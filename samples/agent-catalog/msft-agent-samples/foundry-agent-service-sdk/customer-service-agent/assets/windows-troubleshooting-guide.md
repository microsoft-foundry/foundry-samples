
# 🛠 Windows Troubleshooting Guide

A quick reference for resolving common Windows issues.

---

## 1. System is Slow or Unresponsive

**Symptoms:** Apps freeze, long boot times, unresponsive system.

**Troubleshooting Steps:**
- Restart your computer.
- Open **Task Manager** (`Ctrl + Shift + Esc`) and:
  - End high-resource apps.
  - Disable unnecessary **Startup** programs.
- Run **Disk Cleanup**.
- Scan for malware via **Windows Security**.
- Update Windows and drivers.

---

## 2. Wi-Fi or Network Not Working

**Symptoms:** No internet, Wi-Fi not connecting.

**Troubleshooting Steps:**
- Restart your router and PC.
- Run **Network Troubleshooter**:  
  `Settings > Network & Internet > Status`
- Forget and reconnect to the Wi-Fi.
- Update **Network Adapter** drivers via **Device Manager**.
- Use Command Prompt (Admin):
  ```
  ipconfig /release
  ipconfig /renew
  ```

---

## 3. App Crashes or Won't Open

**Symptoms:** App closes immediately or won’t start.

**Troubleshooting Steps:**
- Restart your PC.
- Run the app as administrator.
- Reinstall or update the app.
- Check **Event Viewer** logs:  
  `Windows Logs > Application`

---

## 4. Windows Update Problems

**Symptoms:** Update errors or stuck installations.

**Troubleshooting Steps:**
- Run **Windows Update Troubleshooter**.
- Clear update cache:
  1. Stop **Windows Update** service (`services.msc`)
  2. Delete contents of `C:\Windows\SoftwareDistribution\Download`
  3. Restart the service
- Manually install updates from [Microsoft Update Catalog](https://www.catalog.update.microsoft.com)

---

## 5. Blue Screen of Death (BSOD)

**Symptoms:** System crashes with a blue screen and error code.

**Troubleshooting Steps:**
- Note the stop code.
- Boot into **Safe Mode**.
- Update drivers.
- Run:
  ```
  sfc /scannow
  chkdsk /f /r
  ```

---

## 6. Display or Graphics Issues

**Symptoms:** Screen flickers, resolution issues, external monitors not working.

**Troubleshooting Steps:**
- Check cable connections.
- Update display drivers.
- Adjust resolution: `Settings > Display`
- Roll back recent driver updates.

---

## 7. Sound Not Working

**Symptoms:** No audio from speakers or headphones.

**Troubleshooting Steps:**
- Check volume and output device settings.
- Restart **Windows Audio** service.
- Update sound drivers.

---

## 8. File Explorer Not Responding

**Symptoms:** File Explorer crashes or freezes.

**Troubleshooting Steps:**
- Restart **Windows Explorer** via Task Manager.
- Clear File Explorer history.
- Disable Quick Access.
- Run `sfc /scannow`.

---

## 9. Peripheral Devices Not Working (USB, Printer, etc.)

**Symptoms:** Devices not detected or malfunctioning.

**Troubleshooting Steps:**
- Try a different port.
- Check **Device Manager** for driver issues.
- Reinstall device drivers.
- For printers: remove and re-add the device.

---

## 10. System Restore or Reset

**Use these options when other steps fail.**

**Options:**
- **System Restore**:  
  `Control Panel > Recovery > Open System Restore`
- **Reset this PC**:  
  `Settings > Update & Security > Recovery > Reset this PC`
