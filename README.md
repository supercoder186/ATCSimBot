# ATC Simulator Bot
This is a "bot" that is designed to play the ATC Simulator available at [atc-sim.com](https://atc-sim.com/)

It guides arriving aircraft to their landing approaches and schedules takeoffs for departing aircraft

## Installation
First run install.bat by double clicking the file. This will download the requirements of the program such as Selenium

Next, you must install the required webdriver. This code is setup to use Firefox. The driver for Firefox can be found [here](https://www.selenium.dev/documentation/webdriver/getting_started/install_drivers/). Ensure your Firefox browser is up to date, then download the latest version of geckodriver and place the exe file named geckodriver.exe in the root folder of your project. Details about using other browsers will be below

## Running the bot
After completing the installation instructions, simply double click the python file main.py to run the bot.

## [Timelapse Demo](https://www.youtube.com/watch?v=-tff-3RKON4)

## Notes 
This code will only work on 1080p resolution & 100% display scaling. The values for the different points on the frame are hardcoded for simplicity.

The code is not tested on Linux / MacOS. It might or might not work

## Using different browsers
Towards the bottom of the file main.py, around line 310 (exact value will vary as the code gets updated), there is a line of code- 
`driver = Firefox()`

This can be changed to use Chrome
`driver = Chrome()`

Note that the corresponding webdriver must be installed. They can be downloaded from [here](https://www.selenium.dev/documentation/webdriver/getting_started/install_drivers/)
