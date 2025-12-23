import _ from "lodash";
import fs from "fs";
import { parse } from "yaml";
import path from "path";
import { Sample } from "./interfaces";
import * as csharp from "./csharp";
import * as go from "./go";
import * as python from "./python";

function parseData(dataPath: string) {
  const dataContent = fs.readFileSync(dataPath, "utf-8");
  try {
    return JSON.parse(dataContent);
  } catch {
    try {
      return parse(dataContent);
    } catch {
      console.error(
        "Failed to parse data file. Please provide a valid JSON or YAML file.",
      );
      process.exit(1);
    }
  }
}

function isDirectory(path: string): boolean {
  return fs.existsSync(path) && fs.lstatSync(path).isDirectory();
}

function resolveSampleFile(samplePath: string): string {
  if (isDirectory(samplePath)) {
    return path.join(samplePath, "sample.yaml");
  }
  return samplePath;
}

function readSample(samplePath: string): Sample {
  const sampleFile = resolveSampleFile(samplePath);
  const fileContents = fs.readFileSync(sampleFile, "utf-8");
  return parse(fileContents) as Sample;
}

function createOutputDirectory(outputPath: string) {
  if (!fs.existsSync(outputPath)) {
    fs.mkdirSync(outputPath, { recursive: true });
  }
}

function isObject(value: any): value is Record<string, any> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function fillInputObject(
  sample: Sample,
  dataPath: string,
): Record<string, any> {
  const inputData = parseData(dataPath);
  if (!isObject(inputData)) {
    console.error("Input data must be an object.");
    process.exit(1);
  }
  const inputObject: Record<string, any> = {};
  for (const { name, required, default: defaultValue } of sample.input) {
    if (name in inputData) {
      /* TODO: Check type */
      inputObject[name] = inputData[name];
    } else {
      if (!required) {
        inputObject[name] = defaultValue;
        continue;
      }
      console.error(`Missing required input: ${name}`);
      process.exit(1);
    }
  }
  return inputObject;
}

const regex = /[ \t]*(<%(?!=)[^%]+%>)\r?\n/g;

function readTemplateFile(templatePath: string): string {
  const template = fs.readFileSync(templatePath, "utf-8");
  return template.replace(regex, "$1");
}

function getProjectFileTemplate(
  sample: Sample,
  options: { useGradle?: boolean; usePoetry?: boolean },
): { targetFileName: string; template: string } {
  const language = sample.type;
  switch (language) {
    case "csharp":
      return {
        targetFileName: `Sample.csproj`,
        template: readTemplateFile(
          path.join(
            __dirname,
            "../project-templates",
            `Sample.csproj.template`,
          ),
        ),
      };
    case "go":
      return {
        targetFileName: `go.mod`,
        template: readTemplateFile(
          path.join(__dirname, "../project-templates", `go.mod.template`),
        ),
      };
    case "javascript":
      return {
        targetFileName: `package.json`,
        template: readTemplateFile(
          path.join(__dirname, "../project-templates", `package.json.template`),
        ),
      };
    case "java":
      if (options.useGradle) {
        return {
          targetFileName: `build.gradle`,
          template: readTemplateFile(
            path.join(
              __dirname,
              "../project-templates",
              `build.gradle.template`,
            ),
          ),
        };
      }
      return {
        targetFileName: `pom.xml`,
        template: readTemplateFile(
          path.join(__dirname, "../project-templates", `pom.xml.template`),
        ),
      };
    case "python":
      if (options.usePoetry) {
        return {
          targetFileName: `pyproject.toml`,
          template: readTemplateFile(
            path.join(
              __dirname,
              "../project-templates",
              `pyproject.toml.template`,
            ),
          ),
        };
      }
      return {
        targetFileName: `requirements.txt`,
        template: readTemplateFile(
          path.join(
            __dirname,
            "../project-templates",
            `requirements.txt.template`,
          ),
        ),
      };
    default:
      console.error(`Unsupported language: ${language}`);
      process.exit(1);
  }
}

function generateProjectFile(
  sample: Sample,
  outputPath: string,
  options: { useGradle?: boolean; usePoetry?: boolean },
) {
  const { targetFileName, template } = getProjectFileTemplate(sample, options);
  const projectFileName = path.join(outputPath, targetFileName);
  const compiledTemplate = _.template(template);
  fs.writeFileSync(
    projectFileName,
    compiledTemplate({
      dependencies: sample.dependencies,
    }),
  );
  console.log(`Generated project file: ${projectFileName}`);
}

function getTargetFileName(sample: Sample): string {
  const language = sample.type;
  switch (language) {
    case "csharp":
      return "Sample.cs";
    case "go":
      return "sample.go";
    case "javascript":
      return "sample.js";
    case "java":
      return "Sample.java";
    case "python":
      return "sample.py";
    default:
      console.error(`Unsupported language: ${language}`);
      process.exit(1);
  }
}

function getSampleTemplate(
  samplePath: string,
  sample: Sample,
): { targetFileName: string; template: string } {
  const language = sample.type;
  if (!language) {
    console.error("Sample type is not defined in the sample file.");
    process.exit(1);
  }
  return {
    targetFileName: getTargetFileName(sample),
    template: readTemplateFile(path.join(samplePath, sample.template)),
  };
}

export function compileSample(
  samplePath: string,
  dataPath: string,
  outputPath: string,
  options: { project: boolean; useGradle: boolean; usePoetry: boolean },
) {
  const sample = readSample(samplePath);
  createOutputDirectory(outputPath);
  if (options.project) {
    generateProjectFile(sample, outputPath, options);
  }

  const inputObject = fillInputObject(sample, dataPath);
  const templateFile = path.join(samplePath, sample.template);
  if (!fs.existsSync(templateFile)) {
    console.error(`Template file not found: ${templateFile}`);
    process.exit(1);
  }

  const { targetFileName, template } = getSampleTemplate(samplePath, sample);
  const outputFilePath = path.join(outputPath, targetFileName);
  const compiledTemplate = _.template(template, {
    imports: {
      csharp: csharp,
      go: go,
      python: python,
    },
  });
  fs.writeFileSync(outputFilePath, compiledTemplate(inputObject));
  console.log(`Generated sample file: ${outputFilePath}`);
}
