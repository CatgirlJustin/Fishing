from PyQt6.QtWidgets import QMainWindow, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
import sys, os, time, threading
import cv2, pyautogui, numpy, keyboard
import json
import ctypes

from modules.SimpleComponents import Button, Label
from modules.GlobalVariables import *
from modules.SettingsWindow import SettingsWindow
from modules.LogsWindow import LogsWindow

# ------------------------
# Utility Functions
# ------------------------
def locateImage(img, threshold: float):
    screenshot = pyautogui.screenshot()
    screenshot = cv2.cvtColor(numpy.array(screenshot), cv2.COLOR_RGB2BGR)
    result = cv2.matchTemplate(screenshot, img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        return max_loc
    return None

def getLastSize() -> list[int]:
    with open("DB.json", "r") as file:
        data = json.load(file)
    size = data["screenSize"][0]
    return [size["width"], size["height"]]

def changeLastSize(newSize: list[int]) -> None:
    with open("DB.json", "r") as file:
        data = json.load(file)
        settings = data["settings"][0]
    newDBobject = {
        "settings": [settings],
        "screenSize": [{"width": newSize[0], "height": newSize[1]}]
    }
    with open('DB.json', 'w') as file:
        json.dump(newDBobject, file)

def changeImageSize(path: str, monitorSize: list[int], lastUsedSize: list[int]) -> None:
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    ratioW = monitorSize[0] / lastUsedSize[0]
    ratioH = monitorSize[1] / lastUsedSize[1]
    targetSize = (int(img.shape[1]*ratioW)+4, int(img.shape[0]*ratioH)+1)
    outIMG = cv2.resize(img, targetSize, cv2.INTER_LINEAR)
    cv2.imwrite(path, outIMG)

# ------------------------
# Main Window
# ------------------------
class MainWindow(QMainWindow):
    def __init__(self, title: str):
        super().__init__()
        self.title = title
        self.icon = APP_ICON
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(self.title)
        self.setWindowIcon(QIcon(self.icon))
        self.setFixedSize(300, 30)
        self.move((screenSize.width() // 2) - (self.width() // 2), 0)
        self.setStyleSheet(CSS)

        # ------------------------
        # State Variables
        # ------------------------
        self.isFishing = False
        self.tryCatchFish = False
        self.shouldStopFishing = False
        self.fishCount = 0
        self.startFishingTimer = 0
        self.startCheckMealTimer = 0
        self.startCheckPotionTimer = 0
        self.maxTimeForWait = 70

        # ------------------------
        # Windows
        # ------------------------
        self.settingsWindow = SettingsWindow(self)
        self.logsWindow = LogsWindow(self)

        # ------------------------
        # UI Buttons
        # ------------------------
        self.btn_start = Button(self, "START", 2, 2, 75, 26, "btn_standart", self.startFishing)
        self.btn_start.setToolTip("Start fishing")
        Button(self, EXIT_ICON, self.width()-28, 2, 26, 26, "btn_red", self.closeEvent).setToolTip("Close window")
        Button(self, SETTING_ICON, self.width()-56, 2, 26, 26, "btn_standart", self.openSettings).setToolTip("Settings window")
        Button(self, LOGS_ICON, self.width()-84, 2, 26, 26, "btn_standart", self.openLogsWindow).setToolTip("History window")
        self.__countLabel = Label(self, 79, 2, 135, 26, "", f"Caught: {self.fishCount}")

        # ------------------------
        # Timer
        # ------------------------
        self.ShouldStopFishingTimer = QTimer(self)
        self.ShouldStopFishingTimer.setInterval(500)
        self.ShouldStopFishingTimer.timeout.connect(self.checkShouldStopFishing)
        self.ShouldStopFishingTimer.start()

        # ------------------------
        # Fishing Thread
        # ------------------------
        self.fishingThread = threading.Thread(target=self.fishing, daemon=True)
        self.fishingThread.start()

    # ------------------------
    # UI Methods
    # ------------------------
    def openSettings(self):
        self.settingsWindow.setVisible(not self.settingsWindow.isVisible())

    def openLogsWindow(self):
        self.logsWindow.setVisible(not self.logsWindow.isVisible())

    def startFishing(self):
        if not self.isFishing:
            self.isFishing = True
            self.startFishingTimer = time.time()
            self.startCheckMealTimer = time.time()
            self.startCheckPotionTimer = time.time()
            self.logsWindow.logs.append([time.localtime(), "start"])
            self.btn_start.setObjectName("btn_red")
            self.btn_start.setText("STOP")
            self.btn_start.setToolTip("Stop fishing")
            self.setStyleSheet(CSS)
        else:
            self.shouldStopFishing = True

    def checkShouldStopFishing(self):
        if self.shouldStopFishing:
            self.isFishing = False
            self.tryCatchFish = False
            self.shouldStopFishing = False
            self.btn_start.setObjectName("btn_standart")
            self.btn_start.setText("START")
            self.btn_start.setToolTip("Start fishing")
            self.logsWindow.logs.append([time.localtime(), "stop"])
            self.setStyleSheet(CSS)

    def closeEvent(self, event=None):
        self.settingsWindow.close()
        self.logsWindow.close()
        self.close()

    # ------------------------
    # Fishing Logic
    # ------------------------
    def fishing(self):
        while self.isVisible():
            if not self.isFishing:
                time.sleep(0.25)
                continue

            elapsed = time.time() - self.startFishingTimer
            mealElapsed = time.time() - self.startCheckMealTimer
            potionElapsed = time.time() - self.startCheckPotionTimer

            # Detect start of fishing
            if locateImage(IMG_START, 0.7) and not self.tryCatchFish:
                self.tryCatchFish = True
                self.startThisTry = time.time()

            # Handle catch
            if self.tryCatchFish:
                self.handleCatch()

            # Timeout
            if elapsed >= self.maxTimeForWait:
                if locateImage(IMG_DISCONNECTED, 0.8):
                    self.shouldStopFishing = True
                else:
                    self.endTry("timeError")

            # Consumables
            if mealElapsed >= self.settingsWindow.mealTimer and self.settingsWindow.useMeal:
                self.consumeMeal()
            if potionElapsed >= self.settingsWindow.potionTimer and self.settingsWindow.usePotion:
                self.consumePotion()

            time.sleep(0.25)

    # ------------------------
    # Handle Catch
    # ------------------------
    def handleCatch(self):
        timeForThisTry = time.time() - self.startThisTry
        caughtSomething = False

        for img, logName in [(IMG_FISH, "fish"), (IMG_JUNK, "fish"),
                             (IMG_TREASURE, "treasure"), (IMG_SUNKEN, "sunken")]:
            if locateImage(img, 0.8) and timeForThisTry <= self.settingsWindow.timeForTry:
                self.endTry(logName)
                if logName in ["fish", "treasure", "sunken"]:
                    self.addFishCount()
                caughtSomething = True
                break

        # Timeout catch
        if timeForThisTry > self.settingsWindow.timeForTry and not caughtSomething:
            self.endTry("timeError")

        # Only click once to reel in
        if not caughtSomething:
            pyautogui.click(button="left")

    # ------------------------
    # End Try
    # ------------------------
 def endTry(self, log: str):
    """
    Handles finishing a catch.
    Reels in the fish and recasts automatically with the same rod/bait.
    """
    if not self.tryCatchFish:
        return
    self.tryCatchFish = False
    self.startFishingTimer = time.time()
    self.logsWindow.logs.append([time.localtime(), log])

    # Step 1: Reel in the catch
    pyautogui.click(button="left")
    time.sleep(0.2)  # small pause to let the game register the reel

    # Step 2: Recast without pressing the rod key
    pyautogui.click(button="left")
    time.sleep(0.1)  # optional tiny delay


    # ------------------------
    # Fish Count
    # ------------------------
    def addFishCount(self):
        self.fishCount += 1
        self.__countLabel.setText(f"Caught: {self.fishCount}")

    def resetFishCount(self):
        self.fishCount = 0
        self.__countLabel.setText(f"Caught: {self.fishCount}")

    # ------------------------
    # Consumables
    # ------------------------
    def consumeMeal(self):
        keyboard.press_and_release(self.settingsWindow.mealKey)
        time.sleep(0.75)
        pyautogui.click(button="left")  # only click, do NOT touch rod
        self.logsWindow.logs.append([time.localtime(), "consumeMeal"])
        self.startFishingTimer = time.time()
        self.startCheckMealTimer = time.time()

    def consumePotion(self):
        keyboard.press_and_release(self.settingsWindow.potionKey)
        time.sleep(0.75)
        pyautogui.click(button="left")  # only click, do NOT touch rod
        self.logsWindow.logs.append([time.localtime(), "consumePotion"])
        self.startFishingTimer = time.time()
        self.startCheckPotionTimer = time.time()


# ------------------------
# Startup
# ------------------------
if __name__ == "__main__":
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()

    app = QApplication(sys.argv)
    screenSize = app.primaryScreen().geometry()

    # Resize images if screen changed
    allImagesPath = [
        Rf'{os.path.abspath(os.path.dirname(sys.argv[0]))}/images/forScript/start.png',
        Rf'{os.path.abspath(os.path.dirname(sys.argv[0]))}/images/forScript/fish.png',
        Rf'{os.path.abspath(os.path.dirname(sys.argv[0]))}/images/forScript/treasure.png',
        Rf'{os.path.abspath(os.path.dirname(sys.argv[0]))}/images/forScript/junk.png',
        Rf'{os.path.abspath(os.path.dirname(sys.argv[0]))}/images/forScript/sunken.png',
        Rf'{os.path.abspath(os.path.dirname(sys.argv[0]))}/images/forScript/disconnected.png'
    ]

    actualScreenSize = [user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)]
    lastUsedSize = getLastSize()
    if lastUsedSize[0] != actualScreenSize[0]:
        for path in allImagesPath:
            changeImageSize(path, actualScreenSize, lastUsedSize)
        changeLastSize(actualScreenSize)

    IMG_START = cv2.imread(allImagesPath[0])
    IMG_FISH = cv2.imread(allImagesPath[1])
    IMG_TREASURE = cv2.imread(allImagesPath[2])
    IMG_JUNK = cv2.imread(allImagesPath[3])
    IMG_SUNKEN = cv2.imread(allImagesPath[4])
    IMG_DISCONNECTED = cv2.imread(allImagesPath[5])

    window = MainWindow("Auto fishing")
    window.show()
    sys.exit(app.exec())
