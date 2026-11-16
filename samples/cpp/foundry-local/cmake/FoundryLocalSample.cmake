include_guard(GLOBAL)

set(FOUNDRY_LOCAL_PACKAGE_ID "Microsoft.AI.Foundry.Local.Runtime")
file(READ "${CMAKE_CURRENT_LIST_DIR}/../packages.config" _foundry_local_packages)
string(REGEX MATCH
  "<package id=\"${FOUNDRY_LOCAL_PACKAGE_ID}\" version=\"([0-9]+\\.[0-9]+\\.[0-9]+)\""
  _foundry_local_package_match
  "${_foundry_local_packages}")
if(NOT CMAKE_MATCH_1)
  message(FATAL_ERROR "Could not read the pinned Foundry Local runtime version.")
endif()
set(FOUNDRY_LOCAL_RUNTIME_VERSION "${CMAKE_MATCH_1}")
set(FOUNDRY_LOCAL_PACKAGES_DIR "${CMAKE_BINARY_DIR}/_packages" CACHE PATH
    "Directory where NuGet restores the Foundry Local runtime")

find_program(NUGET_EXECUTABLE NAMES nuget nuget.exe REQUIRED)

set(_nuget_command
    "${NUGET_EXECUTABLE}" install "${FOUNDRY_LOCAL_PACKAGE_ID}"
    -Version "${FOUNDRY_LOCAL_RUNTIME_VERSION}"
    -OutputDirectory "${FOUNDRY_LOCAL_PACKAGES_DIR}"
    -NonInteractive
    -DirectDownload
    -Verbosity quiet)
if(DEFINED ENV{NUGET_SOURCE} AND NOT "$ENV{NUGET_SOURCE}" STREQUAL "")
  list(APPEND _nuget_command -Source "$ENV{NUGET_SOURCE}")
endif()

execute_process(
  COMMAND ${_nuget_command}
  RESULT_VARIABLE _nuget_result
  COMMAND_ECHO STDOUT)
if(NOT _nuget_result EQUAL 0)
  message(FATAL_ERROR "NuGet package restore failed with exit code ${_nuget_result}")
endif()

set(FOUNDRY_LOCAL_RUNTIME_ROOT
    "${FOUNDRY_LOCAL_PACKAGES_DIR}/${FOUNDRY_LOCAL_PACKAGE_ID}.${FOUNDRY_LOCAL_RUNTIME_VERSION}")
set(FOUNDRY_LOCAL_INCLUDE_DIR "${FOUNDRY_LOCAL_RUNTIME_ROOT}/build/native/include")

if(WIN32)
  if(CMAKE_GENERATOR_PLATFORM)
    set(_foundry_local_target_arch "${CMAKE_GENERATOR_PLATFORM}")
  elseif(CMAKE_VS_PLATFORM_NAME)
    set(_foundry_local_target_arch "${CMAKE_VS_PLATFORM_NAME}")
  elseif(CMAKE_CXX_COMPILER_ARCHITECTURE_ID)
    set(_foundry_local_target_arch "${CMAKE_CXX_COMPILER_ARCHITECTURE_ID}")
  else()
    set(_foundry_local_target_arch "${CMAKE_SYSTEM_PROCESSOR}")
  endif()
  string(REGEX REPLACE ",.*$" "" _foundry_local_target_arch "${_foundry_local_target_arch}")
  string(TOLOWER "${_foundry_local_target_arch}" _foundry_local_target_arch)

  if(_foundry_local_target_arch MATCHES "^(arm64|aarch64)$")
    set(FOUNDRY_LOCAL_RID "win-arm64")
  elseif(_foundry_local_target_arch MATCHES "^(x64|amd64|x86_64)$")
    set(FOUNDRY_LOCAL_RID "win-x64")
  else()
    message(FATAL_ERROR
      "Unsupported Windows target architecture: ${_foundry_local_target_arch}. "
      "Foundry Local supports x64 and ARM64.")
  endif()
  set(FOUNDRY_LOCAL_LIBRARY
      "${FOUNDRY_LOCAL_RUNTIME_ROOT}/runtimes/${FOUNDRY_LOCAL_RID}/native/foundry_local.lib")
  set(_native_pattern "*.dll")
elseif(APPLE)
  if(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)$")
    message(FATAL_ERROR "Microsoft.AI.Foundry.Local.Runtime supports macOS on Apple silicon only.")
  endif()
  set(FOUNDRY_LOCAL_RID "osx-arm64")
  set(FOUNDRY_LOCAL_LIBRARY
      "${FOUNDRY_LOCAL_RUNTIME_ROOT}/runtimes/${FOUNDRY_LOCAL_RID}/native/libfoundry_local.dylib")
  set(_native_pattern "*.dylib")
elseif(UNIX)
  if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(ARM64|arm64|aarch64)$")
    set(FOUNDRY_LOCAL_RID "linux-arm64")
  else()
    set(FOUNDRY_LOCAL_RID "linux-x64")
  endif()
  set(FOUNDRY_LOCAL_LIBRARY
      "${FOUNDRY_LOCAL_RUNTIME_ROOT}/runtimes/${FOUNDRY_LOCAL_RID}/native/libfoundry_local.so")
  set(_native_pattern "*.so*")
else()
  message(FATAL_ERROR "Unsupported platform for the Foundry Local runtime package.")
endif()

if(NOT EXISTS "${FOUNDRY_LOCAL_INCLUDE_DIR}/foundry_local/foundry_local_cpp.h")
  message(FATAL_ERROR "Foundry Local C++ headers were not restored.")
endif()
if(NOT EXISTS "${FOUNDRY_LOCAL_LIBRARY}")
  message(FATAL_ERROR "Foundry Local native library was not restored for ${FOUNDRY_LOCAL_RID}.")
endif()

file(GLOB_RECURSE FOUNDRY_LOCAL_NATIVE_ASSETS CONFIGURE_DEPENDS
     "${FOUNDRY_LOCAL_PACKAGES_DIR}/*/runtimes/${FOUNDRY_LOCAL_RID}/native/${_native_pattern}")

function(add_foundry_local_sample target)
  add_executable("${target}" main.cpp)
  target_compile_features("${target}" PRIVATE cxx_std_20)
  target_include_directories("${target}" PRIVATE "${FOUNDRY_LOCAL_INCLUDE_DIR}")
  target_link_libraries("${target}" PRIVATE "${FOUNDRY_LOCAL_LIBRARY}")

  set_target_properties("${target}" PROPERTIES
    CXX_EXTENSIONS OFF
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_BINARY_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO "${CMAKE_BINARY_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL "${CMAKE_BINARY_DIR}")

  if(APPLE)
    set_target_properties("${target}" PROPERTIES BUILD_RPATH "@loader_path")
  elseif(UNIX)
    set_target_properties("${target}" PROPERTIES BUILD_RPATH "$ORIGIN")
    target_link_libraries("${target}" PRIVATE dl pthread)
  endif()

  foreach(_asset IN LISTS FOUNDRY_LOCAL_NATIVE_ASSETS)
    add_custom_command(TARGET "${target}" POST_BUILD
      COMMAND "${CMAKE_COMMAND}" -E copy_if_different
              "${_asset}" "$<TARGET_FILE_DIR:${target}>"
      VERBATIM)
  endforeach()

  if(APPLE)
    add_custom_command(TARGET "${target}" POST_BUILD
      COMMAND "${CMAKE_COMMAND}" -E create_symlink
              "libonnxruntime.dylib"
              "$<TARGET_FILE_DIR:${target}>/libonnxruntime.1.dylib"
      VERBATIM)
  elseif(UNIX)
    add_custom_command(TARGET "${target}" POST_BUILD
      COMMAND "${CMAKE_COMMAND}" -E rm -f
              "$<TARGET_FILE_DIR:${target}>/libonnxruntime.so.1"
      COMMAND "${CMAKE_COMMAND}" -E create_symlink
              "libonnxruntime.so"
              "$<TARGET_FILE_DIR:${target}>/libonnxruntime.so.1"
      VERBATIM)
  endif()
endfunction()
