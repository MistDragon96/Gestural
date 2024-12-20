import os
import time
import keyboard
import threading
import socket
import json
import pyautogui
import math
import logging
import subprocess
from pynput.mouse import Controller
from multiprocessing import shared_memory
from screeninfo import get_monitors

from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume


screen_width, screen_height = get_monitors()[0].width, get_monitors()[0].height  # Get monitor's dimensions
mouse = Controller()

time.sleep(1.5)

HOST = '127.0.0.1'  # Localhost
PORT = 65433        # New port for functionality.py to listen on

gesture_data_lock = threading.Lock()
shutdown_event = threading.Event()
update_event = threading.Event()

dir = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(dir, "state.txt"), "w") as file:             # to tell if the functionality program is running or not
    file.write("True")

hold = 0.75                   #For how long must the gesture be hold to be given a positive to execute

# Global buffer for smoothing
cursor_buffer = []

#Connects to the shared memory created by the gesture_to_list_vectors.py
shared_memory = shared_memory.SharedMemory(name='pointer_status')

devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(
    IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = cast(interface, POINTER(IAudioEndpointVolume))

logging.basicConfig(  # Configure logging
    filename=os.path.join(dir, "Gesture.log"),
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def validate_config(config):
    if "landmarks" not in config or len(config['landmarks']) != 21 or "distance" not in config:
        with open(os.path.join(dir, "config_backup.json"), "r") as config_file:  # To read the backup configuration file
            return json.load(config_file)
        
    else:
        return config

# Configuration
try:
    with open(os.path.join(dir, "config.json"), "r") as config_file:  # To read the configuration file
        config = json.load(config_file)
        config = validate_config(config)

except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Error reading configuration file: {e}, \n using backup.")
    logging.error(f"Functionality Error: Error reading configuration file: {e}, \n using backup.")
    with open(os.path.join(dir, "config_backup.json"), "r") as config_file:  # To read the backup configuration file
        config = json.load(config_file)

config_dist = config['distance']

config_0_to_9 = config_dist["0_to_9"]

def start_receiver():
    global gesture_data, hand_result, landmarks

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((HOST, PORT))
            server_socket.listen()
            print(f"Server listening on {HOST}:{PORT}")

            conn, addr = server_socket.accept()
            with conn:
                print(f"Connected by {addr}")

                # Buffer to store partial data
                buffer = ""

                while not shutdown_event.is_set():  # Check for shutdown signal
                    data = conn.recv(1024)  # Receive up to 1024 bytes
                    if not data:
                        break
                    # Append new data to buffer
                    buffer += data.decode('utf-8')

                    # Process complete messages (split by '\n')
                    while '\n' in buffer:
                        # Split on the first occurrence of the delimiter
                        message, buffer = buffer.split('\n', 1)
                        try:
                            # Parse JSON message
                            gesture_data = json.loads(message)

                            with gesture_data_lock:
                                gesture_data.update(gesture_data)
                                hand_result = gesture_data['hand_result']
                                landmarks = gesture_data['landmarks']
                            update_event.set()
                            update_event.clear()
                                

                        except json.JSONDecodeError as e:
                            print(f"Invalid JSON received. Error: {e}")
                            logging.error(f"Functionality Error: Invalid JSON received. Error: {e}")

    except Exception as e:
        print(f"Error receiving data: {e}")
        logging.error(f"Functionality Error: Error receiving data: {e}")


def shutter():
    global gesture_data, hand_result
    while True:
        time.sleep(0.5)
        try:
            if hand_result[1:] == [True, True, True, False, False] and not (calib_distance(distance(landmarks[4], landmarks[16])) <= config_dist["4_to_16_pointer"] + 0.004):
                time_start = time.time()

                while time.time() <= time_start + hold:
                    if hand_result[1:] != [True, True, True, False, False]:
                        break
                
                else:
                    print("Signal Detected")
                    with gesture_data_lock:
                        gesture_data['hand_result'] = [False, False, False, False, False]  # Reset the signal
                    shutdown_event.set()
                    break

        except KeyError as e:
            print(f"KeyError: {e}, gesture_data may not contain 'hand_result'")
            logging.error(f"Functionality Error: KeyError: {e}, gesture_data may not contain 'hand_result'")


        except Exception as e:
            print(f"An error occure: {e}")
            logging.error(f"Functionality Error: An error occure: {e}")


def reset_gesture_data():
    global gesture_data, gesture_data_lock, hand_result
    # Reset the gesture to prevent multiple triggers
    with gesture_data_lock:
        gesture_data['hand_result'][1:] = [False, False, False, False, False]
        hand_result[1:] = [False, False, False, False, False]

def change_desktop(direction):
    if os.name == 'nt':  # Windows
        if direction == "right":
            pyautogui.hotkey('ctrl', 'win', 'right')
        elif direction == "left":
            pyautogui.hotkey('ctrl', 'win', 'left')


def distance(a,b):
    length = (b['x']-a['x'])**2 + (b['y']-a['y'])**2
    return length
    
def calib_distance(length):
    c,d=landmarks[0], landmarks[9]
    return (length * config_0_to_9 / distance(c,d))


def map_cursor(index_tip, roi_x_max, roi_x_min, roi_y_max, roi_y_min):
    #Maps the index finger tip coordinates to the screen cursor position.
    
    global cursor_buffer

    try:
        index_tip_x = max(roi_x_min, min(roi_x_max, index_tip['x']))
        index_tip_y = max(roi_y_min, min(roi_y_max, index_tip['y']))

        # Map the position within the smaller rectangle (ROI) to the entire screen
        normalized_x = (index_tip_x - roi_x_min) / (roi_x_max - roi_x_min)
        normalized_y = (index_tip_y - roi_y_min) / (roi_y_max - roi_y_min)

        # Convert normalized coordinates to screen coordinates
        cursor_x = int(normalized_x * screen_width)
        cursor_y = int(normalized_y * screen_height)

        # Add the new position to the buffer for smoothing
        cursor_buffer.append((cursor_x, cursor_y))

        # Keep only the last N positions (N = 10 here)
        if len(cursor_buffer) > 10:
            cursor_buffer.pop(0)

        # Calculate the average position for smooth movement
        avg_x = int(sum(pos[0] for pos in cursor_buffer) / len(cursor_buffer))
        avg_y = int(sum(pos[1] for pos in cursor_buffer) / len(cursor_buffer))

        # Move the mouse cursor smoothly
        mouse.position = (avg_x, avg_y)


    except IndexError as e:
        print(f"Error accessing landmarks: {e}")
        logging.error(f"Functionality Error: Error accessing landmarks: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        logging.error(f"Functionality Error: An unexpected error occurred: {e}")

def pointer():
    shared_memory.buf[0] = 1
    # Define the region of interest (ROI) in normalized coordinates
    roi = 0.45
    roi_x_min = (1.0 - roi) / 2
    roi_x_max = roi_x_min + (roi)
    roi_y_min = (1.0 - roi) / 2 - 0.2
    roi_y_max = roi_y_min + (roi) - 0.2

    flag = True

    #Continuously map the index finger tip to the screen cursor position while the pointer gesture is detected.
    try:
        while True:
            if hand_result[1:6] != [False, True, True, False, False]:
                time_start = time.time()

                while time.time() <= time_start + hold:
                    if hand_result[1:6] == [False, True, True, False, False]:
                        break
                else:
                    break

            if len(landmarks) > 8:  # Ensure landmark for index tip is available
                if update_event.wait(timeout = 2):
                    if calib_distance(distance(landmarks[8], landmarks[12])) <= config_dist["8_to_12_pointer"] + 0.0015 and flag:
                        map_cursor(landmarks[8], roi_x_max, roi_x_min, roi_y_max, roi_y_min)
                    elif calib_distance(distance(landmarks[8], landmarks[12])) >= config_dist["8_to_12_pointer_open"] and flag:
                        flag = False
                else:
                    reset_gesture_data()
            else:
                print("Landmarks data is incomplete or invalid.")
                break

            if not flag:
                if calib_distance(distance(landmarks[8], landmarks[12])) <= config_dist["8_to_12_pointer"] + 0.0015:
                    flag = True
                    pyautogui.click()
                    print("clicked!")
            
            time.sleep(0.01)  # Small delay to improve CPU performance
    except Exception as e:
        print(f"Error in pointer function: {e}")
        logging.error(f"Functionality Error: Error in pointer function: {e}")
    
    finally:
        shared_memory.buf[0] = 0


def set_system_volume(change):
    new_volume = max(0.0, min(1.0, change/100))  # Clamp between 0 and 1
    volume.SetMasterVolumeLevelScalar(new_volume, None)

def volume_mode():
    """Activate volume mode and adjust volume based on the index tip's x-coordinate shift."""
    pyautogui.moveTo(1750,1050)
    pyautogui.click()
    volume_range = [0.4,0.6]
    try:
        while True:
            current_x = landmarks[8]['x']
            # Restrict detection to a small middle area (e.g., 0.4 to 0.6)
            
            s = 1 / (volume_range[1] - volume_range[0]) #scaling factor
                
            v = (current_x - volume_range[0]) / (volume_range[1] - volume_range[0])
            # Adjust system volume based on delta_x
            volume_change = int(v*100)  # Map x-shift to volume scale
            set_system_volume(volume_change)  # Implement this function to adjust volume
            
            initial_x = current_x  # Update for continuous tracking

            if hand_result[3:] != [True, True, True] or not(calib_distance(distance(landmarks[4], landmarks[8])) <= config_dist["4_to_8_pinch"] + 0.004) or not(update_event.wait(timeout=2)):  # Exit if gesture is no longer active
                print("Ending volume mode")
                break


    except Exception as e:
        print(f"Error in volume mode: {e}")
        logging.error(f"Functionality Error: Error in volume mode: {e}")

    finally:
        pyautogui.moveTo(1750,1050)
        pyautogui.click()


def r_or_l():
    if landmarks[4]['x'] > landmarks[2]['x']:
        pyautogui.hotkey('right')
    else:
        pyautogui.hotkey('left')

def main_loop():
    global gesture_data,gesture_data_lock, hand_result, landmarks

    try:
        if hand_result[2:6] == [True, True, True, False] and calib_distance(distance(landmarks[4],landmarks[20])) <= config_dist["4_to_20_swipe"]+0.005:
            print("Swipe hand mode detected")
            if len(landmarks) > 0:
                x = config_dist['12_swipe_left']*0.75
                start_x = landmarks[12]['x'] # x-coordinate of tip of middle finger
                time.sleep(0.35)
                update_event.wait()
                end_x = landmarks[12]['x'] # x-coordinate of tip of middle finger

                if end_x - start_x > x:  # Adjust threshold as needed
                    print("Swipe Left")
                    change_desktop("left")#thinking about making it 0.5
                elif start_x - end_x > x:
                    print("Swipe Right")
                    change_desktop("right")

            reset_gesture_data()


        elif hand_result[2:6] == [True, True, False, False] and calib_distance(distance(landmarks[8], landmarks[12])) <= config_dist["8_to_12_pointer"] + 0.002 and distance(landmarks[4], landmarks[16]) <= config_dist["4_to_16_pointer"] + 0.003:
            time_start = time.time()


            while time.time() <= time_start + hold:
                if hand_result[2:6] != [True, True, False, False] or not(calib_distance(distance(landmarks[4], landmarks[16])) <= config_dist["4_to_16_pointer"] + 0.003) or not(distance(landmarks[8], landmarks[12]) <= config_dist["8_to_12_pointer"] + 0.002):
                    break

            else:
                print("Pointer gesture activated.")
                pointer()
            
            reset_gesture_data()


        elif hand_result[3:] == [True, True, True] and calib_distance(distance(landmarks[4], landmarks[8])) <= config_dist["4_to_8_pinch"] + 0.001:
            time_start = time.time()


            while time.time() <= time_start + hold:
                if hand_result[3:] != [True, True, True] or not(calib_distance(distance(landmarks[4], landmarks[8])) <= config_dist["4_to_8_pinch"] + 0.001):
                    break

            else:
                print("Volume gesture activated.")
                volume_mode()
            
            reset_gesture_data()


        elif hand_result[1:] == [True, False, False, False, False]:
            r_or_l()
            reset_gesture_data()

        
        elif hand_result[1:] == [False, True, True, True, True]:
            print("Lock Swipe Mode detected.")
            if len(landmarks) > 0:
                x = config_dist['12_swipe_down']*0.5
                start_y = landmarks[12]['y'] # x-coordinate of tip of middle finger
                time.sleep(0.5)
                update_event.wait()
                end_y = landmarks[12]['y'] # x-coordinate of tip of middle finger

                if end_y - start_y > x:  # Adjust threshold as needed
                    print("Swipe Down")
                    # Lock screen command for Windows
                    os.system("rundll32.exe user32.dll,LockWorkStation")

            reset_gesture_data()

        
        #Jarvis Gesture ( Jarvis(Leo) Under development)
        #elif hand_result[2:6] == [True, True, False, False] and calib_distance(distance(landmarks[8], landmarks[12])) >= config_dist["8_to_12_pointer_open"] and distance(landmarks[4], landmarks[16]) <= config_dist["4_to_16_pointer"] + 0.003:
        #    time_start = time.time()
        #
        #
        #    while time.time() <= time_start + hold:
        #        if not(hand_result[2:6] == [True, True, False, False] and calib_distance(distance(landmarks[8], landmarks[12])) >= config_dist["8_to_12_pointer_open"] and distance(landmarks[4], landmarks[16]) <= config_dist["4_to_16_pointer"] + 0.003):
        #            break
        #
        #    else:
        #        print("Jarvis gesture activated.")
        #        jarvis_process = subprocess.Popen(['python', 'E:\\Coding\\Jarvis\\Jarvis.py'])
        #        
        #        time.sleep(10)
        #
        #        if shared_memory.buf[1] == 1:
        #            jarvis_process.kill()
        #        
        #    
        #    reset_gesture_data()

    except Exception as e:
        print(f"Error in the Main_loop: {e}")
        logging.error(f"Functionality Error: Error in the Main_loop: {e}")
        


if __name__ == "__main__":
    gesture_data = {'hand_result':[], "landmarks": []}
    gesture_data_copy = gesture_data.copy()

    hand_result = gesture_data["hand_result"]

    landmarks = gesture_data["landmarks"]

    # Start the receiver thread
    receiver_thread = threading.Thread(target=start_receiver)
    receiver_thread.daemon = True  # Allow the thread to terminate when the main program exits
    receiver_thread.start()

    shutter_thread = threading.Thread(target=shutter)
    shutter_thread.daemon = True  # Allow the thread to terminate when the main program exits
    shutter_thread.start()
    
    try:
        while not shutdown_event.is_set():
            main_loop()
    
    finally:
        
        with open(os.path.join(dir, "state.txt"), "w") as file:             # to tell if the functionality program is running or not
            file.write("")
        shared_memory.buf[0] = 0
        shared_memory.close()