import logging
from PyQt5.QtCore import QThread, pyqtSlot, pyqtSignal
import time
import subprocess, re
import globals

DEFAULT_ISO=320
DEFAULT_SHUTTER_SPEED="1/60"
DEFAULT_FOCUS_MODE="Automatic"
DEFAULT_WHITEBALANCE_MODE="Flash"
DEFAULT_F_NUMBER="f/2.8"

class CameraInitializer(QThread):
    enable_buttons_signal = pyqtSignal(bool)

    def __init__(self, window):
        super().__init__()

    def run(self):
        # init camera and repeat in case False is returned
        while not self.initCamera():
            logging.info("Trying to init camera again")
            time.sleep(5)
        self.enable_buttons_signal.emit(True)

    def initCamera(self) -> bool:

            # run gphoto2 --auto-detect and analyse output for detected cameras
            process = subprocess.Popen(["gphoto2", "--auto-detect"], stdout=subprocess.PIPE)
            out, err = process.communicate()
            out = out.decode()
            cameras = out.split("\n")
            #extract camera names
            # Define the regular expression pattern to match the camera name
            pattern = r"^(.*?)\s+usb:\d+,\d+"
            cameras = [re.search(pattern, c, re.MULTILINE) for c in cameras]

            # filter out none matching lines (e.g. empty lines)
            cameras = list(filter(None, cameras))

            # if more than one camera was detected use the first one
            if len(cameras) >= 1:
                globals.CURRENT_CAMERA = cameras[0].group(1).strip()
            else:
                logging.warning("No camera detected")
                return False

            logging.info(f"Using camera: {globals.CURRENT_CAMERA}")

            # if camera name contains Sony call method to init sony camera
            if "Sony" in globals.CURRENT_CAMERA:
                logging.info("Sony camera detected")
                # somehow the first command issued with gphoto2 will not work correctly on Sony cameras. So we issue it two times.
                settfirsEmptyCommand = subprocess.Popen(["gphoto2", "--set-config", f"/main/imgsettings/iso={DEFAULT_ISO}", "--camera", globals.CURRENT_CAMERA])
                settfirsEmptyCommand.communicate()
                time.sleep(0.5)

                settingIso = subprocess.Popen(["gphoto2", "--set-config", f"/main/imgsettings/iso={DEFAULT_ISO}", "--camera", globals.CURRENT_CAMERA])
                # wait for completion
                settingIso.communicate()
                # check if a error occured
                if settingIso.returncode != None and settingIso.returncode != 0:
                    logging.error(f"Error setting ISO: {settingIso}")
                else:
                    logging.info(f"ISO set to {DEFAULT_ISO}")
                time.sleep(0.5)

                settingShutter = subprocess.Popen(["gphoto2", "--set-config", f"/main/capturesettings/shutterspeed={DEFAULT_SHUTTER_SPEED}", "--camera", globals.CURRENT_CAMERA])
                # wait for completion
                settingShutter.communicate()
                if settingShutter.returncode != None and settingShutter.returncode != 0:
                    logging.error(f"Error setting shutter speed: {settingShutter}")
                else:
                    logging.info(f"Shutter speed set to {DEFAULT_SHUTTER_SPEED}")
                time.sleep(0.5)
            
                settingFocusMode = subprocess.Popen(["gphoto2", "--set-config", f"/main/capturesettings/focusmode={DEFAULT_FOCUS_MODE}", "--camera", globals.CURRENT_CAMERA])
                # wait for completion
                settingFocusMode.communicate()
                if settingFocusMode.returncode != None and settingFocusMode.returncode != 0:
                    logging.error(f"Error setting focus mode: {settingFocusMode}")
                else:
                    logging.info(f"Focus mode set to {DEFAULT_FOCUS_MODE}")
                time.sleep(0.5)

                settingWhiteBalance = subprocess.Popen(["gphoto2", "--set-config", f"/main/imgsettings/whitebalance={DEFAULT_WHITEBALANCE_MODE}", "--camera", globals.CURRENT_CAMERA])
                # wait for completion
                settingWhiteBalance.communicate()
                if settingWhiteBalance.returncode != None and settingWhiteBalance.returncode != 0:
                    logging.error(f"Error setting whitebalance mode: {settingWhiteBalance}")
                else:
                    logging.info(f"Whitebalance mode set to {DEFAULT_WHITEBALANCE_MODE}")
                time.sleep(0.5)

                settingFNumber = subprocess.Popen(["gphoto2", "--set-config", f"/main/capturesettings/f-number={DEFAULT_F_NUMBER}", "--camera", globals.CURRENT_CAMERA])
                # wait for completion
                settingFNumber.communicate()
                if settingFNumber.returncode != None and settingFNumber.returncode != 0 or  settingFNumber.stdout != None and "Error" in settingFNumber.stdout:
                    logging.error(f"Error setting f number: {settingFNumber}")
                else:
                    logging.info(f"F-Number set to {DEFAULT_F_NUMBER}")
                time.sleep(0.5)

            return True