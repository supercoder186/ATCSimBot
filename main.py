from selenium.webdriver import Firefox, Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import ElementNotInteractableException
import numpy as np
import time
import re
import math

TAKEOFF_QUEUE = 0
DEPARTURE = 1
ARRIVAL = 2
APPROACHING = 3

# Plane States is an array that stores the state of each plane in play
# It has a list of sub-arrays corresponding to each possible state
# 0 - planes waiting to takeoff - (Callsign, Runway, Destination)
# 1 - planes departing
# 2 - planes being guided to their final approach
# 3 - planes on final approach
# Each index will contain an array of each plane in that state
plane_states = [[], [], [], []]
taking_off = []
speeding_up = []
intercepting = {}
arrival_states = {}


# Position of BNN VOR
POS_BNN = (818, 722)
# Target points with 09 landing runway
TARGET_POINTS_09_N = [(350, 800), (350, 600)]
TARGET_POINTS_09_S = [(350, 250), (350, 450)]
# Target points with 27 landing runway
TARGET_POINTS_27_N = [(1350, 800), (1350, 600)]
TARGET_POINTS_27_S = [(1350, 250), (1350, 450)]
# Target points
target_points = []
landing_rwy = ''
target_rwy = ''

# Functions to help find intersection of plane paths
def check_headings(point1,bearing1,point2,bearing2,intsec):
    c = 450*math.pi/180
    if (math.cos(c-(bearing1*math.pi/180))*(intsec[0]-point1[0]) > 0 or math.sin(c-(bearing1*math.pi/180))*(intsec[1]-point1[1]) > 0) and (math.cos(c-(bearing2*math.pi/180))*(intsec[0]-point2[0]) > 0 or math.sin(c-(bearing2*math.pi/180))*(intsec[1]-point2[1]) > 0):
        return intsec # function returns a tuple with intersection (x,y) or None if there will be no intersection
    else:
        return None

def find_intersection(point1,bearing1,point2,bearing2): # points to be given in tuple (x,y), bearing in degrees
    if bearing1 != 0:
        gradient1 = math.tan((math.pi/2)-(bearing1*math.pi/180)) # equation in both x and y
        eq1 = np.array([1,-gradient1, point1[1]-(gradient1*point1[0])])
    else:
        # equation only in x
        eq1 = np.array([0,1, point1[0]])
    if bearing2 != 0:
        gradient2 = math.tan((math.pi/2)-(bearing2*math.pi/180)) # equation in both x and y
        eq2 = np.array([1,-gradient2, point2[1]-(gradient2*point2[0])])
    else:
        # equation only in x
        eq2 = np.array([0,1, point2[0]])
    
    aug = np.array([eq1[-1],eq2[-1]])
    augMatrix = np.array([eq1[:-1],eq2[:-1]])
    try:
        solution = np.linalg.solve(augMatrix,aug)
        intsec = (solution[1],solution[0])
        return check_headings(point1,bearing1,point2,bearing2,intsec) #returns tuple of intersection point or None
    except np.linalg.LinAlgError:
        return None

# Parse the data shown on the 'strips' on the right side of the screen
def parse_plane_strips(html):
    global plane_states

    plane_states = [[], [], [], []]

    # Regex expression to parse the strips of the planes waiting to takeoff
    to_queue_expression = \
        r'<div id="(.+?)" name="\1".+? rgb\(192, 228, 250\);">\1 &nbsp;(\d{1,2}[LR]).+?To: (.{3,6})<'
    for match in re.findall(to_queue_expression, html):
        # print('Departure Callsign: {}, Runway: {}, Destination: {}'.format(match[0], match[1], match[2]))
        plane_states[TAKEOFF_QUEUE].append([match[0], match[1], match[2]])

    # Regex expression to parse the strips of the planes climbing to cruise
    departure_expression = r'<div id="(.+?)" name="\1".+? rgb\(192, 228, 250\);">\1 &nbsp;(\D.+?) '
    for match in re.findall(departure_expression, html):
        # print('Departure Callsign: {}, Destination: {}'.format(match[0], match[1]))
        plane_states[DEPARTURE].append([match[0], match[1]])
        if match[0] in taking_off:
            taking_off.remove(match[0])

    # Regex expression to parse the strips of the planes descending towards the airport
    arrival_expression = r'<div id="(.+?)" name="\1".+? rgb\(252, 240, 198\);">\1 &nbsp;(\w[A-Z]{2,5}|\d{2,3}°)'
    for match in re.findall(arrival_expression, html):
        # print('Arrival Callsign: {}, Heading: {}'.format(match[0], match[1]))
        plane_states[ARRIVAL].append([match[0], match[1].replace('°', '')])

    # Regex expression to parse the strips of the planes on approach
    approach_expression = r'<div id="(.+?)" name="\1".+? rgb\(252, 240, 198\);">\1 &nbsp;((?:9|27)[LR])'
    for match in re.findall(approach_expression, html):
        # print('Approach Callsign: {}, Runway: {}'.format(match[0], match[1]))
        plane_states[APPROACHING].append([match[0], match[1]])
        if match[0] in arrival_states.keys():
            arrival_states.pop(match[0])
        if match[0] in intercepting.keys():
            intercepting.pop(match[0])


# Parse the data shown on the radar screen
def parse_canvas(html):
    parse_expression = r'<div id="(.+?)" class="SanSerif12".+?left: (.+?)px; top: (.+?)px.*\1<br>(\d{3}).(\d{2})'
    for match in re.findall(parse_expression, html):
        callsign = match[0]
        # Iterate through each plane to find the matching callsign and then append the values of x, y and alt
        # Quite inefficient but it works because there are only around 10 - 20 planes tops
        # Might update indexing later to make this prettier
        for category in plane_states:
            for plane in category:
                if plane[0] == callsign:
                    plane.append(int(match[1]) + 25)
                    plane.append(950 - int(match[2]))
                    plane.append(int(match[3]) * 100)
                    plane.append(int(match[4]))


# Calculate the heading a plane needs to take to get from its current pos to a point
def calculate_heading(pos1, pos2):
    dx = pos2[0] - pos1[0]
    dy = pos2[1] - pos1[1]

    initial_hdg = math.degrees(math.atan2(dx, dy))
    if initial_hdg < 0:
        initial_hdg += 360

    return round(initial_hdg)


# Calculate the squared distance between 2 points
def calculate_sqr_distance(pos1, pos2):
    dx = pos2[0] - pos1[0]
    dy = pos2[1] - pos1[1]

    sqr_d = (dx ** 2) + (dy ** 2)
    return sqr_d


def get_command_list():
    command_list = []
    # Index 0 is Left Rwy, Index 1 is Right Rwy
    safe_runways = [True, True]

    # First find if it is safe for a plane to takeoff
    # Check if the previous departure has achieved a particular speed in its takeoff run
    # When the plane reaches this speed it will have reached 1000 feet before the previous planes' departure
    for departure in plane_states[DEPARTURE]:
        if 'BEE' in departure[0] and departure[1] == 'BUZAD' and departure[4] == 200:
            command_list.append('{} C 11 EX'.format(departure[0]))

        if len(departure) >= 6 and departure[4] < 200:
            safe_runways = [False, False]

    for approaching in plane_states[APPROACHING]:
        if len(approaching) >= 5 and approaching[4] < 900:
            if 'L' in approaching[1]:
                safe_runways[0] = False
            elif 'R' in approaching[1]:
                safe_runways[1] = False

    # Clear planes for takeoff accordingly
    for rto in plane_states[TAKEOFF_QUEUE]:
        if 'L' in rto[1] and safe_runways[0]:
            callsign = rto[0]
            if not callsign in taking_off:
                destination = rto[2]
                command_list.append(
                    '{} C {} C 11 T'.format(callsign, destination))
                taking_off.append(callsign)

            safe_runways[0] = False
        elif 'R' in rto[1] and safe_runways[1]:
            callsign = rto[0]
            if not callsign in taking_off:
                destination = rto[2]
                command_list.append(
                    '{} C {} C 11 T'.format(callsign, destination))

                taking_off.append(callsign)

            safe_runways[1] = False

    # Stores the squared distances to final
    distances_to_final = {}

    # Calculate headings for each plane on the approaching list
    for arrival in plane_states[ARRIVAL]:
        global target_rwy

        callsign = arrival[0]
        plane_heading = int(arrival[1])
        plane_pos = (arrival[2], arrival[3])

        if plane_pos[1] < 500:
            if landing_rwy == '9':
                target_points = TARGET_POINTS_09_S
                intercept_hdg = 45
            else:
                target_points = TARGET_POINTS_27_S
                intercept_hdg = 315
        else:
            if landing_rwy == '9':
                target_points = TARGET_POINTS_09_N
                intercept_hdg = 135
            else:
                target_points = TARGET_POINTS_27_N
                intercept_hdg = 225

        if not callsign in arrival_states:
            if landing_rwy == '27':
                if plane_pos[1] > 200 and plane_pos[1] < 800 and plane_pos[0] > 1350:
                    arrival_states[callsign] = 1
                    command_list.append('{} C 2 EX'.format(callsign))
                else:
                    arrival_states[callsign] = 0
                    command_list.append('{} C 4'.format(callsign))
            else:
                if plane_pos[1] > 200 and plane_pos[1] < 800 and plane_pos[0] < 350:
                    arrival_states[callsign] = 1
                    command_list.append('{} C 2 EX'.format(callsign))
                else:
                    arrival_states[callsign] = 0
                    command_list.append('{} C 4'.format(callsign))

        elif arrival_states[callsign] == len(target_points):
            command_list.append('{} L {}'.format(
                callsign, intercepting[callsign]))
            continue

        if arrival_states[callsign] >= 0:
            target_point = target_points[arrival_states[callsign]]
        else:
            target_point = POS_BNN

        sqr_distance_to_target = calculate_sqr_distance(
            plane_pos, target_point)
        distances_to_final[callsign] = sqr_distance_to_target

        if arrival_states[callsign] <= 0:
            distances_to_final[callsign] += 40000

        if arrival_states[callsign] < 0:
            distances_to_final[callsign] += calculate_sqr_distance(POS_BNN,
                                                                   TARGET_POINTS_09_N[0] if landing_rwy == '9' else TARGET_POINTS_27_N[0])

        # Check if the plane is near the target point
        if sqr_distance_to_target < 1000:
            arrival_states[callsign] += 1

            command_list.append('{} C {}'.format(
                callsign, 4 - arrival_states[callsign]))
            # Check if the plane is at the last point
            if arrival_states[callsign] == len(target_points):
                if 'L' in target_rwy:
                    target_rwy = target_rwy.replace('L', 'R')
                else:
                    target_rwy = target_rwy.replace('R', 'L')
                hdg_str = str(intercept_hdg)
                if len(hdg_str) < 3:
                    hdg_str = '0' + hdg_str

                command_list.append('{} C {}'.format(callsign, hdg_str))
                command_list.append('{} L {}'.format(callsign, target_rwy))
                intercepting[callsign] = target_rwy
                continue

        target_heading = calculate_heading(plane_pos, target_point)

        if abs(target_heading - plane_heading) > 5:
            hdg_str = str(target_heading)
            while len(hdg_str) < 3:
                hdg_str = '0' + hdg_str

            command_list.append('{} C {}'.format(arrival[0], hdg_str))

    # Ensure proper separation of arrival aircraft
    for arrival in plane_states[ARRIVAL]:
        if len(arrival) < 6:
            continue

        callsign = arrival[0]

        if arrival_states[callsign] == len(target_points):
            continue

        plane_pos = (arrival[2], arrival[3])
        speed = arrival[5] * 10
        clear_max_speed = True

        for arrival_2 in plane_states[ARRIVAL]:
            callsign_2 = arrival_2[0]

            if len(arrival_2) < 6 or callsign_2 == callsign:
                continue

            plane_2_pos = (arrival_2[2], arrival_2[3])

            if arrival_states[callsign_2] == len(target_points):
                continue

            distance_btw_planes = calculate_sqr_distance(
                plane_pos, plane_2_pos)

            if distance_btw_planes < 100 ** 2:
                if distances_to_final[callsign_2] < distances_to_final[callsign]:
                    clear_max_speed = False

                    break

        if clear_max_speed and speed < 240 and not callsign in speeding_up:
            command_list.append('{} S 240'.format(callsign))
            speeding_up.append(callsign)
        elif not clear_max_speed and (speed == 240 or callsign in speeding_up):
            command_list.append('{} S 160'.format(callsign))
            if callsign in speeding_up:
                speeding_up.remove(callsign)
        elif speed == 240 and callsign in speeding_up:
            speeding_up.remove(callsign)

    # Ensure approaching planes are at 160 knots
    for approaching in plane_states[APPROACHING]:
        if len(approaching) < 6:
            continue

        callsign = approaching[0]
        alt = approaching[4]
        speed = approaching[5] * 10
        if speed < 160 and alt > 900:
            command_list.append('{} S 160'.format(callsign))

    # Ensure approaching planes don't collide
    for approaching in plane_states[APPROACHING]:
        if len(approaching) < 5:
            continue

        callsign = approaching[0]
        rwy = approaching[1]
        pos = (approaching[2], approaching[3])
        for approaching_2 in plane_states[APPROACHING]:
            callsign_2 = approaching_2[0]
            rwy_2 = approaching_2[1]

            if len(approaching_2) < 4 or callsign == callsign_2 \
                    or rwy != rwy_2:
                continue

            plane_2_pos = (approaching_2[2], approaching_2[3])

            distance_btw_planes = calculate_sqr_distance(
                pos, plane_2_pos)

            # Order go-around if dangerously close, go to BNN from where the plane will be re-sequenced
            if distance_btw_planes < 17 ** 2:
                if approaching[4] == approaching_2[4]:
                    if ('27' in rwy and (pos[0] > plane_2_pos[0])) or \
                            ('9' in rwy and (pos[0] < plane_2_pos[0])):
                        command_list.append('{} A C 7 EX C {}'.format(callsign,
                                                                      calculate_heading(pos, POS_BNN)))
                        arrival_states[callsign] = -1
                elif approaching[4] > approaching_2[4]:
                    command_list.append('{} A C 7 EX C {}'.format(callsign,
                                                                  calculate_heading(pos, POS_BNN)))
                    arrival_states[callsign] = -1

    return command_list


def execute_commands(commands):
    for command in commands:
        print("Executing command:", command)
        command_input.send_keys(command)
        command_input.send_keys(Keys.ENTER)


if __name__ == '__main__':
    # Start up firefox and open the website
    driver = Firefox()
    driver.maximize_window()
    driver.get('http://atc-sim.com/')

    # Change the airport and start the game
    driver.find_element(by=By.XPATH,
                        value='/html/body/div[4]/div[1]/form/table/tbody/tr/td[1]/div[1]/select/option[4]').click()
    '''driver.find_element(by=By.XPATH,
                        value='//*[@id="frmOptions"]/table/tbody/tr/td[1]/div[7]/select/option[3]').click()'''
    driver.find_element(by=By.XPATH,
                        value='//*[@id="frmOptions"]/table/tbody/tr/td[1]/input[1]').click()
    time.sleep(1)

    failed = True
    while failed:
        try:
            driver.find_element(
                by=By.XPATH, value='//*[@id="btnclose"]').click()
            failed = False
        except ElementNotInteractableException:
            time.sleep(1)

    wind_dir = int(driver.find_element(by=By.XPATH,
                                       value='/html/body/div[1]/div/div[9]/div[1]').get_attribute('innerHTML').split('<br>')[1].replace('°', ''))

    # Check if the landing runway is 09 or 27
    if abs(90 - wind_dir) < abs(270 - wind_dir):
        landing_rwy = '9'
        target_rwy = '9L'
    else:
        landing_rwy = '27'
        target_rwy = '27R'

    command_input = driver.find_element(by=By.XPATH,
                                        value='//*[@id="canvas"]/div[1]/div/form/input[1]')

    while True:
        driver.switch_to.frame('ProgressStrips')
        strips_text = driver.find_element(by=By.XPATH,
                                          value='//*[@id="strips"]').get_attribute('innerHTML')
        parse_plane_strips(strips_text)
        driver.switch_to.parent_frame()
        canvas_text = driver.find_element(by=By.XPATH,
                                          value='//*[@id="canvas"]').get_attribute('innerHTML')
        parse_canvas(canvas_text)
        command_list = get_command_list()
        execute_commands(command_list)
        time.sleep(2)
