from dataclasses import dataclass
from enum import Enum
from typing import List


DEFAULT_WELCOME_MESSAGE = "Willkommen zur Fotobox"
DEFAULT_TARGET_DIR = "data/images"
DEFAULT_COUNTDOWN_TIME_SECONDS = 5
DEFAULT_PREVIEW_TIME_SECONDS = 20
DEFAULT_SHOW_COLLAGE = True
DEFAULT_SHOW_DELETE = True
DEFAULT_SHOW_RECAPTURE = True
DEFAULT_SHOW_PRINT = False
DEFAULT_SHOW_SHARE = False
DEFAULT_SHOW_BUTTON_TEXT = False
DEFAULT_BACKGROUND_IMAGE = "backgrounds/Landingpage.png"
DEFAULT_CAMERA_INDEX = 0
DEFAULT_COUNTDOWN_SOUND = "ui/sounds/countdown_ping.wav"
DEFAULT_WELCOME_TEXT_COLOR = "rgb(247, 244, 183)"
DEFAULT_IMAGE_BORDER_COLOR = "rgb(247, 244, 183)"


def init():
    global CURRENT_CAMERA
    CURRENT_CAMERA = None

    global SETTINGS
    # Settings are read from settings.yaml. Adjust them there or in GUI by long pressing the welcome message
    SETTINGS = {
        "WELCOME_MESSAGE": DEFAULT_WELCOME_MESSAGE,
        "TARGET_DIR": DEFAULT_TARGET_DIR,
        "COUNTDOWN_TIME_SECONDS": DEFAULT_COUNTDOWN_TIME_SECONDS,
        "PREVIEW_TIME_SECONDS": DEFAULT_PREVIEW_TIME_SECONDS,
        "SHOW_COLLAGE": DEFAULT_SHOW_COLLAGE,
        "SHOW_DELETE": DEFAULT_SHOW_DELETE,
        "SHOW_RECAPTURE": DEFAULT_SHOW_RECAPTURE,
        "SHOW_PRINT": DEFAULT_SHOW_PRINT,
        "SHOW_SHARE": DEFAULT_SHOW_SHARE,
        "SHOW_BUTTON_TEXT": DEFAULT_SHOW_BUTTON_TEXT,
        "BACKGROUND_IMAGE": DEFAULT_BACKGROUND_IMAGE,
        "CAMERA_INDEX": DEFAULT_CAMERA_INDEX,
        "COUNTDOWN_SOUND": DEFAULT_COUNTDOWN_SOUND,
        "BACKGROUND_IMAGE": DEFAULT_BACKGROUND_IMAGE,
        "WELCOME_TEXT_COLOR": DEFAULT_WELCOME_TEXT_COLOR,
        "IMAGE_BORDER_COLOR": DEFAULT_IMAGE_BORDER_COLOR
    }

    global FREEZE_STREAM
    FREEZE_STREAM = False

    global FILE_NAME
    FILE_NAME = ""
    
    global CAPTURE_MODE
    CAPTURE_MODE = None
    
    global CURRENT_COLLAGE
    CURRENT_COLLAGE = None
    
class CaptureMode(Enum):
    SINGLE = 1
    COLLAGE = 2
    
@dataclass
class Coordinates:
    def __init__(self, x, y):
        self.x = x
        self.y = y

@dataclass
class Size:
    width: int
    height: int

@dataclass
class ImagePosition:
    id: int
    position: Coordinates
    size: Size
    imagePath: str = None

@dataclass
class Collage:
    name: str
    images: List[ImagePosition]
    currentImage: int = 0
