from libs_py import LiquidCrystal, analogRead

# Constants

SCREEN_NUMBER_COLS = 16
SCREEN_NUMBER_ROWS = 2

MENU_ITEMS = ("START CAPTURE", "START SHOWCASE" ,"PRESETS", "SET TRIGGER", "SETTINGS", "ABOUT", 'TEST')

class ScreenHandler:

    current_selection = 0

    def __init__(self, screen_number_cols: int, screen_number_rows: int, menu_items: list, lcd: LiquidCrystal):
        self.lcd = lcd
        self.screen_number_cols = screen_number_cols
        self.screen_number_rows = screen_number_rows
        self.menu_items = menu_items
        
    def drawMainMenu(self):
        self.lcd.clear()

        # Writing current selection indicator
        self.lcd.setCursor(0, 0)
        self.lcd.print(">")

        for i, item in enumerate(self.menu_items[self.current_selection:self.current_selection + self.screen_number_rows]):
            self.lcd.setCursor(1, i)
            self.lcd.print(item)

        # Writing up arrow indicator if we're not on the first item
        if self.current_selection != 0:
            self.lcd.setCursor(self.screen_number_cols - 1, 0)
            self.lcd.write(1)

        # Writing down arrow indicator if we're not on the last item
        if self.current_selection != len(self.menu_items):
            self.lcd.setCursor(self.screen_number_cols - 1, self.screen_number_rows)
            self.lcd.write(2)

    def evaluateButton(self, x):
        """This function is called whenever a button press is evaluated.
        The LCD shield works by observing a voltage drop across the buttons all
        hooked up to A0."""
        result = 0
        if x < 50:
            result = -1  # up
        elif x < 195:
            result = 1  # down
        return result    

    def operateMainMenu(self):
        pin_volt = analogRead(0)
        new_selection = self.current_selection + self.evaluateButton(pin_volt)

        if new_selection != self.current_selection and new_selection > 0 and new_selection < len(self.menu_items):
            self.current_selection = new_selection
            self.drawMainMenu()

lcd = LiquidCrystal(8, 9, 4, 5, 6, 7)
screen = ScreenHandler(SCREEN_NUMBER_COLS, SCREEN_NUMBER_ROWS, MENU_ITEMS, lcd)

def setup():
    pass

def loop():
    screen.operateMainMenu()

def main():
    setup()
    while True:
        loop()

main()