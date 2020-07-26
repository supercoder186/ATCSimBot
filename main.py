from selenium.webdriver import Chrome
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import ElementNotInteractableException
import time
import re
import random

# Start up chrome and open the website
driver = Chrome()
driver.maximize_window()
driver.get('http://atc-sim.com/')

# Change the airport and start the game
driver.find_element_by_xpath('/html/body/div[4]/div[1]/form/table/tbody/tr/td[1]/div[1]/select/option[4]').click()
# driver.find_element_by_xpath('//*[@id="frmOptions"]/table/tbody/tr/td[1]/div[7]/select/option[4]').click()
driver.find_element_by_xpath('//*[@id="frmOptions"]/table/tbody/tr/td[1]/input[1]').click()
time.sleep(3)

failed = True
while failed:
    try:
        driver.find_element_by_xpath('//*[@id="btnclose"]').click()
        failed = False
    except ElementNotInteractableException:
        time.sleep(1)

command_input = driver.find_element_by_xpath('//*[@id="canvas"]/div[1]/div/form/input[1]')
takeOffQueue = {}
arrivals = {}
onApproach = {}
departures = {}
plane_states = {}
cleared = False


def parse_plane_strips(html):
    global cleared

    plane_states.clear()
    departures.clear()
    onApproach.clear()
    to_queue_expression = \
        '<div id="(.+?)" name="\\1".+? rgb\\(192, 228, 250\\);">\\1 &nbsp;(\\d{1,2}[LR]).+?To: (.{3,6})<'
    for match in re.findall(to_queue_expression, html):
        # print('Departure Callsign: {}, Runway: {}, Destination: {}'.format(match[0], match[1], match[2]))
        takeOffQueue[match[0]] = [match[1], match[2]]
        plane_states[match[0]] = 0

    departure_expression = '<div id="(.+?)" name="\\1".+? rgb\\(192, 228, 250\\);">\\1 &nbsp;(\\D.+?) '
    for match in re.findall(departure_expression, html):
        # print('Departure Callsign: {}, Destination: {}'.format(match[0], match[1]))
        if match[0] in takeOffQueue:
            takeOffQueue.pop(match[0])
            cleared = False

        departures[match[0]] = [match[1]]
        plane_states[match[0]] = 1

    arrival_expression = '<div id="(.+?)" name="\\1".+? rgb\\(252, 240, 198\\);">\\1 &nbsp;(\\w[A-Z]{2,5}|\\d{2,3}°)'
    for match in re.findall(arrival_expression, html):
        # print('Arrival Callsign: {}, Heading: {}'.format(match[0], match[1]))
        arrivals[match[0]] = [match[1].replace('°', '')]
        plane_states[match[0]] = 2

    approach_expression = '<div id="(.+?)" name="\\1".+? rgb\\(252, 240, 198\\);">\\1 &nbsp;((?:9|27)[LR])'
    for match in re.findall(approach_expression, html):
        # print('Approach Callsign: {}, Destination: {}'.format(match[0], match[1]))
        onApproach[match[0]] = [match[1]]
        plane_states[match[0]] = 3


def parse_canvas(html):
    parse_expression = '<div id="(.+?)" class="SanSerif12".+?left: (.+?)px; top: (.+?)px.*\\1<br>(\\d{3})'
    for match in re.findall(parse_expression, html):
        callsign = match[0]
        if match[0] in plane_states:
            state = plane_states[callsign]
        else:
            return

        if state == 1:
            departures[callsign].append(int(match[3]))
        elif state == 2:
            arrivals[callsign].append(int(match[1]))
            arrivals[callsign].append(int(match[2]))
            arrivals[callsign].append(int(match[3]))


def get_command_list():
    global cleared
    commands = []

    # Takeoff commands
    can_takeoff = True
    for callsign in departures:
        plane = departures[callsign]
        if (len(plane) > 1 and plane[1] <= 5) or len(plane) <= 1:
            can_takeoff = False
            break

    if can_takeoff and len(takeOffQueue) >= 1 and not cleared:
        callsign = random.choice(list(takeOffQueue.keys()))
        commands.append("{} C {} C 11 T".format(callsign, takeOffQueue[callsign][1]))
        cleared = True

    # Landing commands
    print(arrivals)
    return commands


def execute_commands(commands):
    for command in commands:
        print("Executing command:", command)
        command_input.send_keys(command)
        command_input.send_keys(Keys.ENTER)


while True:
    print('-----------------------------')
    driver.switch_to.frame('ProgressStrips')
    strips_text = driver.find_element_by_xpath('//*[@id="strips"]').get_attribute('innerHTML')
    parse_plane_strips(strips_text)
    driver.switch_to.parent_frame()
    canvas_text = driver.find_element_by_xpath('//*[@id="canvas"]').get_attribute('innerHTML')
    parse_canvas(canvas_text)
    command_list = get_command_list()
    execute_commands(command_list)
    time.sleep(2)
