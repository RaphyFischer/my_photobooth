from datetime import datetime
import logging
import os
import subprocess
from threading import Timer
import time
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, QObject
import globals
import asyncio
import aiofiles
import PySide6.QtAsyncio as QtAsyncio


class CaptureWorker(QObject):
    progress = pyqtSignal(int)
    capture_finished = pyqtSignal()
    preview_finished = pyqtSignal()
    countdown = 0
    capture_error = pyqtSignal(str)
    countdown_timer = None

    def cancel_preview_timer(self):
        if self.preview_timer is not None:
            self.preview_timer.cancel()

    def countdown_elapsed(self):
        if self.countdown == 0:
            self.countdown_timer.cancel()
            self.countdown_timer = None
            self.run_async(self.capture_image())
        else:
            self.progress.emit(self.countdown)
            self.countdown -= 1
            self.countdown_timer = Timer(1,self.countdown_elapsed)
            self.countdown_timer.start()


    async def capture_image(self):
        logging.info('Capturing image')
        globals.FILE_NAME = os.path.join(globals.SETTINGS["TARGET_DIR"], "photobox_%s.jpg" %datetime.now().strftime("%m%d%Y_%H%M%S"))
        
        logging.info(f"Capturing image to {globals.FILE_NAME}")

        logging.info("Starting capture")
        args = ["gphoto2", "--filename",globals.FILE_NAME, "--capture-image-and-download", "--force-overwrite", "--keep", "--camera", globals.CURRENT_CAMERA]

        if globals.CURRENT_CAMERA is not None and "Canon" in globals.CURRENT_CAMERA and "M3" in globals.CURRENT_CAMERA:
            args += ["--set-config", "chdk=On"]

        captureProc = subprocess.Popen(args)
        # wait for completion
        captureProc.communicate()
        # check exit code of captureProc
        if captureProc.returncode != None and captureProc.returncode != 0:
            logging.error(f"Error capturing image: {captureProc}")
            self.capture_error.emit("Error capturing image")
            return

        globals.FREEZE_STREAM = True

        # wait for image to transfer from camera to device
        try:
            await asyncio.wait_for(self.wait_for_file(globals.FILE_NAME), timeout=10.0)
        except asyncio.TimeoutError:
            logging.error(f"timeout when waiting for file with name: {globals.FILE_NAME} to be present")
            self.capture_error.emit()
            return

        # start the preview countdown timer
        self.start_preview_countdown()
        self.capture_finished.emit()
        

    @pyqtSlot()
    def run(self):

        if globals.CURRENT_CAMERA is None:
            logging.error("Camera is not detected yet. Unable to take a photo")
            self.capture_error.emit("Camera is not detected yet. Unable to take a photo")
            return
        
        self.countdown = globals.SETTINGS["COUNTDOWN_TIME_SECONDS"]
        logging.info("Countdown started")

        # set back timer in case there is still one active
        if self.countdown_timer is not None and self.countdown_timer.isActive():
            self.countdown_timer.cancel()
            self.countdown_timer = None

        self.countdown_timer = Timer(1,self.countdown_elapsed)
        #self.countdown_timer.setInterval(1000)
        #self.countdown_timer.timeout.connect()

        # manually trigger first countdown_elapsed call
        self.progress.emit(self.countdown)
        self.countdown -= 1

        self.countdown_timer.start()


    def start_preview_countdown(self):
        self.preview_timer = Timer(globals.SETTINGS["PREVIEW_TIME_SECONDS"],self.on_preview_finished)
        self.preview_timer.start()  

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
        self.preview_timer.cancel()
        self.preview_timer = None
        logging.info("preview time finished. Returning to start screen")
        self.preview_finished.emit()

    async def wait_for_file(self,file_path, check_interval=1):
        logging.info(f"Waiting for file {file_path} to be present")
        while True:
            if os.path.exists(file_path):
                return True
            await asyncio.sleep(check_interval)

    def run_async(self,future, as_task=True):
        """
        A better implementation of `asyncio.run`.

        :param future: A future or task or call of an async method.
        :param as_task: Forces the future to be scheduled as task (needed for e.g. aiohttp).
        """

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # no event loop running:
            loop = asyncio.new_event_loop()
            return loop.run_until_complete(self._to_task(future, as_task, loop))


    def _to_task(self,future, as_task, loop):
        if not as_task or isinstance(future, asyncio.Task):
            return future
        return loop.create_task(future)