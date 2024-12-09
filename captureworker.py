from datetime import datetime
import logging
import os
import subprocess
import time
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QTimer, QObject
import globals


class CaptureWorker(QObject):
    progress = pyqtSignal(int)

    def __init__ (self):
        super().__init__()
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.on_preview_finished)
        self.preview_countdown = globals.SETTINGS["PREVIEW_TIME_SECONDS"]*1000

    @pyqtSlot()
    def run(self):
        global SETTINGS

        if globals.CURRENT_CAMERA is None:
            logging.error("Camera is not detected yet. Unable to take a photo")
            self.progress.emit(-2)
            return
        
        logging.info("Countdown started")
        #subprocess.Popen(["gphoto2", "--reset"])
        for secs_left in range(globals.SETTINGS["COUNTDOWN_TIME_SECONDS"], 0, -1):
            self.progress.emit(secs_left)
            time.sleep(1)

        logging.info('Capturing image')
        globals.SETTINGS["FILE_NAME"] = os.path.join(globals.SETTINGS["TARGET_DIR"], "photobox_%s.jpg" %datetime.now().strftime("%m%d%Y_%H%M%S"))

        logging.info("Starting capture")
        args = ["gphoto2", "--filename", globals.SETTINGS["FILE_NAME"], "--capture-image-and-download", "--force-overwrite", "--keep", "--camera", globals.CURRENT_CAMERA]

        if globals.CURRENT_CAMERA is not None and "Canon" in globals.CURRENT_CAMERA and "M3" in globals.CURRENT_CAMERA:
            args += ["--set-config", "chdk=On"]

        captureProc = subprocess.Popen(args)
        # wait for completion
        captureProc.communicate()
        # check exit code of captureProc
        if captureProc.returncode != None and captureProc.returncode != 0:
            logging.error(f"Error capturing image: {captureProc}")
            return
        
        # send 0 for "click"
        self.progress.emit(1)
        time.sleep(1)
        self.progress.emit(0)
        globals.SETTINGS["FREEZE_STREAM"] = True

        # TODO introduce timeout for waiting for file
        # wait for image to transfer from camera to device
        while not os.path.isfile(globals.SETTINGS["FILE_NAME"]):
            time.sleep(0.2)

        # and -1 for shutter icon
        self.progress.emit(-1)
        
        logging.info('Showing preview')
        
        self.start_preview_countdown()

        logging.info("preview time finished. Returning to start screen")

        logging.info("preview time finished. Returning to start screen 2222")

        globals.SETTINGS["FREEZE_STREAM"] = False
        logging.info("emitting -2")
        self.progress.emit(-2)

    def start_preview_countdown(self):
        self.preview_timer.start(self.preview_countdown)  

    def ensureTargetDirExists(self):
        # check if target dir exists if not existing create it. If creation fails use default dir
        try:
            os.makedirs(globals.SETTINGS["TARGET_DIR"],exist_ok=True)
        except :
            logging.error(f"Couldn't create {globals.SETTINGS['TARGET_DIR']} using default dir instead: {globals.DEFAULT_TARGET_DIR}")
            globals.SETTINGS["TARGET_DIR"] = globals.DEFAULT_TARGET_DIR
            try:
                os.makedirs(globals.SETTINGS["TARGET_DIR"],exist_ok=True)
            except:
                logging.error(f"Couldn't create {globals.SETTINGS['TARGET_DIR']}")
                self.progress.emit(-2)
                return

    def on_preview_finished(self):
        logging.info("preview time finished. Returning to start screen")
        globals.SETTINGS["FREEZE_STREAM"] = False
        logging.info("emitting -2")
        self.progress.emit(-2)