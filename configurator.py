import cv2
import mediapipe as mp
import json
import socket
import keyboard
import os
import math
import time 

HOST = '127.0.0.1'  # Server's IP address
PORT = 65432        # Port to connect to

margin = 0.025
a = False
b = 0
r = False

dir = os.path.dirname(os.path.abspath(__file__))

# Initialize Mediapipe Hands solution
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# Setup Webcam
cap = cv2.VideoCapture(0)

with open(os.path.join(dir, "config.json"), "r") as config_file:  # To read the configuration file
    config = json.load(config_file)

def distance(a,b):
    length = math.hypot(b.x-a.x,b.y-a.y)
    return length

with mp_hands.Hands(model_complexity=0, min_detection_confidence=0.7, min_tracking_confidence=0.6) as hands:
    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break

            # Flip and process the frame
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)

            # Get frame dimensions
            frame_height, frame_width, _ = frame.shape

            if results.multi_hand_landmarks:
                for hand_landmarks, hand_classification in zip(results.multi_hand_landmarks, results.multi_handedness):
                    # Draw landmarks (always display landmarks)
                    mp_drawing.draw_landmarks(
                        frame, 
                        hand_landmarks, 
                        mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style()
                    )

                    
                    if not a:
                        a_frame = frame

                    if keyboard.is_pressed('a') and (not a):
                        print("a detected")
                        gesture_data = config
                        if  b == 0:
                            a = True
                            lm = hand_landmarks.landmark
                            gesture_data = {
                                        "landmarks": [
                                            {"x": landmark.x, "y": landmark.y, "z": landmark.z}
                                            for landmark in hand_landmarks.landmark
                                        ],
                                        "distance":{"0_to_9":distance(lm[0],lm[9])**2, "4_to_8":distance(lm[4],lm[8])**2}
                                    }
                        elif b == 1:
                            a = True
                            lm = hand_landmarks.landmark
                            gesture_data["distance"].update({"4_to_8_pinch":distance(lm[4], lm[8])**2})
                        elif b == 2:
                            a = True
                            lm = hand_landmarks.landmark
                            gesture_data["distance"].update({"8_to_12_pointer":distance(lm[8],lm[12])**2})
                        elif b == 3:
                            a = True
                            lm = hand_landmarks.landmark
                            gesture_data["distance"].update({"8_to_12_pointer_open":distance(lm[8],lm[12])**2})
                        elif b == 4:
                            a = True
                            lm = hand_landmarks.landmark
                            gesture_data["distance"].update({"4_to_20_swipe":distance(lm[4],lm[20])**2})
                        elif b==5:
                            lm = hand_landmarks.landmark
                            swipe_start = lm[12]
                            b+=1
                            print("swipe down")
                            a = False
                            time.sleep(1)
                        elif b==6:
                            a = True
                            lm = hand_landmarks.landmark
                            gesture_data["distance"].update({"12_swipe_down":distance(swipe_start,lm[12])})
                        elif b == 7:
                            lm = hand_landmarks.landmark
                            swipe_start = lm[12]
                            b+=1
                            print("swipe left")
                            a = False
                            time.sleep(1)
                        elif b == 8:
                            a = True
                            lm = hand_landmarks.landmark
                            gesture_data["distance"].update({"12_swipe_left":distance(swipe_start,lm[12])})
                        elif b == 9:
                            a = True
                            lm = hand_landmarks.landmark
                            gesture_data["distance"].update({"4_to_16_point":distance(lm[4],lm[16])**2})
                    

                    if (keyboard.is_pressed('w') and a) or r:
                            r = False
                            print("w detected")
                            a = False
                            b+=1
                            if b == 1:
                                print("thumb to index pinch")
                            elif b == 2:
                                print("index middle pointer mode (index middle touching). [0,1,1,0,0]")
                            elif b == 3:
                                print("index middle open pointer mode(index middle seperated). [0,1,1,0,0]")
                            elif b == 4:
                                print("thumb pinky swipe mode. [0,1,1,1,0]")
                            elif b ==5:
                                print("middle swipe down. [0,1,1,1,1]")
                            elif b == 7:
                                print("middle swipe left. [0,1,1,1,0]")
                            elif b == 9:
                                print("thumb ring pointer mode. [0,1,1,0,0]")
                            elif b>7:
                                with open(os.path.join(dir, "config.json"), "w") as file:
                                    file.write(str(json.dumps(gesture_data)))
                                    print("Done.")

                    if keyboard.is_pressed('r') and a:
                        print("r detected")
                        b-=1
                        r = True


            if not a:
                cv2.imshow("Hand Detection", frame)
            else:
                cv2.imshow("Hand Detection", a_frame)

            if cv2.waitKey(1) and keyboard.is_pressed('ctrl') and keyboard.is_pressed('q'):
                break

    except Exception as e:
        print(f"An Error occured {e}")

cap.release()
cv2.destroyAllWindows()
print("Client Exited Gracefully")