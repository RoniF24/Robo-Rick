import cv2
import mediapipe as mp
import math
import time
import os


mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils


# האם לפתוח חלון מצלמה?
# אם אין DISPLAY בלינוקס, לא ננסה לפתוח חלון כדי למנוע קריסה של Qt/xcb.
SHOW_CAMERA_WINDOW = bool(os.environ.get("DISPLAY"))

# כמה פריימים רצופים צריך כדי להחליט שהפקודה יציבה
STABLE_FRAMES_REQUIRED = 3

# גבולות אזורי המסך
LEFT_ZONE = 0.40
RIGHT_ZONE = 0.60

# סף לזיהוי יד פתוחה עם אצבעות כלפי מטה
PALM_DOWN_THRESHOLD = 0.08

# מהירות/עוצמת תנועה התחלתית
FORWARD_STEP = 2
BACKWARD_STEP = 5
TURN_SPEED = 10

# כמה זמן לעצור לפני שינוי כיוון
STOP_BEFORE_DIRECTION_CHANGE_SECONDS = 0.5

# פקודות שנחשבות תנועה
MOVEMENT_COMMANDS = {
    "MOVE_FORWARD",
    "MOVE_BACKWARD",
    "TURN_RIGHT",
    "TURN_LEFT"
}


def distance(point1, point2):
    """
    מחשב מרחק בין שתי נקודות של MediaPipe.
    """

    return math.sqrt(
        (point1.x - point2.x) ** 2 +
        (point1.y - point2.y) ** 2
    )


def get_open_finger_states(hand_landmarks):
    """
    מחזיר אילו אצבעות פתוחות.
    הבדיקה מבוססת על מרחק משורש כף היד,
    כדי שתעבוד גם כשהיד הפוכה עם אצבעות כלפי מטה.
    """

    landmarks = hand_landmarks.landmark
    wrist = landmarks[0]

    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    middle_tip = landmarks[12]
    ring_tip = landmarks[16]
    pinky_tip = landmarks[20]

    thumb_base = landmarks[2]
    index_base = landmarks[5]
    middle_base = landmarks[9]
    ring_base = landmarks[13]
    pinky_base = landmarks[17]

    thumb_open = distance(wrist, thumb_tip) > distance(wrist, thumb_base) * 1.25
    index_open = distance(wrist, index_tip) > distance(wrist, index_base) * 1.25
    middle_open = distance(wrist, middle_tip) > distance(wrist, middle_base) * 1.25
    ring_open = distance(wrist, ring_tip) > distance(wrist, ring_base) * 1.25
    pinky_open = distance(wrist, pinky_tip) > distance(wrist, pinky_base) * 1.25

    return {
        "thumb": thumb_open,
        "index": index_open,
        "middle": middle_open,
        "ring": ring_open,
        "pinky": pinky_open
    }


def count_open_fingers_from_states(finger_states):
    """
    סופר כמה אצבעות פתוחות.
    """

    count = 0

    for is_open in finger_states.values():
        if is_open:
            count += 1

    return count


def is_v_sign(finger_states):
    """
    מזהה סימן V:
    אצבע מורה ואמה פתוחות,
    קמיצה וזרת סגורות.
    את האגודל לא מחייבים, כי לפעמים הוא מזוהה שונה.
    """

    return (
        finger_states["index"]
        and finger_states["middle"]
        and not finger_states["ring"]
        and not finger_states["pinky"]
    )


def classify_gesture(finger_states):
    """
    מסווג את מצב היד:
    V_SIGN = חזרה למצב קול
    OPEN_HAND = יד פתוחה
    FIST = אגרוף
    UNKNOWN = לא ברור
    """

    open_fingers = count_open_fingers_from_states(finger_states)

    if is_v_sign(finger_states):
        return "V_SIGN"

    if open_fingers >= 4:
        return "OPEN_HAND"

    if open_fingers <= 1:
        return "FIST"

    return "UNKNOWN"


def get_hand_center(hand_landmarks):
    """
    מחזיר את מרכז היד לפי ממוצע נקודות היד.
    הערכים בין 0 ל-1.
    """

    landmarks = hand_landmarks.landmark

    x_sum = 0
    y_sum = 0

    for point in landmarks:
        x_sum += point.x
        y_sum += point.y

    center_x = x_sum / len(landmarks)
    center_y = y_sum / len(landmarks)

    return center_x, center_y


def is_open_hand_pointing_down(hand_landmarks):
    """
    מזהה יד פתוחה הפוכה:
    קצות האצבעות נמצאים מתחת לשורש כף היד.
    במסך: y גדול יותר = נמוך יותר.
    """

    landmarks = hand_landmarks.landmark
    wrist_y = landmarks[0].y

    fingertips = [8, 12, 16, 20]
    avg_fingertips_y = sum(landmarks[i].y for i in fingertips) / len(fingertips)

    return avg_fingertips_y > wrist_y + PALM_DOWN_THRESHOLD


def decide_follow_command(raw_gesture, center_x, hand_landmarks):
    """
    מחליט על פקודת Follow לפי מצב היד והמיקום שלה.
    """

    if raw_gesture == "NO_HAND":
        return "STOP_NO_HAND"

    if raw_gesture == "V_SIGN":
        return "VOICE_MODE"

    if raw_gesture == "FIST":
        return "STOP"

    if raw_gesture == "UNKNOWN":
        return "WAIT"

    # מכאן והלאה: יד פתוחה

    if is_open_hand_pointing_down(hand_landmarks):
        return "MOVE_BACKWARD"

    # בגלל cv2.flip(frame, 1), מחליפים ימין/שמאל
    # כדי שהכלב יעקוב אחרי היד שלך בפועל.
    if center_x < LEFT_ZONE:
        return "TURN_RIGHT"

    if center_x > RIGHT_ZONE:
        return "TURN_LEFT"

    return "MOVE_FORWARD"


def dog_forward(dog):
    """
    קדימה.
    אם קיימת forward נשתמש בה, אחרת move.
    """

    if hasattr(dog, "forward"):
        dog.forward(FORWARD_STEP)
    else:
        dog.move('x', FORWARD_STEP)


def dog_back(dog):
    """
    אחורה.
    אם קיימת back נשתמש בה, אחרת move עם ערך שלילי.
    """

    if hasattr(dog, "back"):
        dog.back(BACKWARD_STEP)
    else:
        dog.move('x', -BACKWARD_STEP)


def dog_turn_right(dog):
    """
    פנייה ימינה.
    אם קיימת turnright נשתמש בה, אחרת turn עם ערך שלילי.
    """

    if hasattr(dog, "turnright"):
        dog.turnright(TURN_SPEED)
    else:
        dog.turn(-TURN_SPEED)


def dog_turn_left(dog):
    """
    פנייה שמאלה.
    אם קיימת turnleft נשתמש בה, אחרת turn עם ערך חיובי.
    """

    if hasattr(dog, "turnleft"):
        dog.turnleft(TURN_SPEED)
    else:
        dog.turn(TURN_SPEED)


def send_robot_command(dog, command):
    """
    כאן נמצאות פקודות הכלב האמיתיות.
    """

    if command == "MOVE_FORWARD":
        print("DOG COMMAND: forward")
        dog_forward(dog)

    elif command == "MOVE_BACKWARD":
        print("DOG COMMAND: back")
        dog_back(dog)

    elif command == "TURN_RIGHT":
        print("DOG COMMAND: turn right")
        dog_turn_right(dog)

    elif command == "TURN_LEFT":
        print("DOG COMMAND: turn left")
        dog_turn_left(dog)

    elif command == "STOP":
        print("DOG COMMAND: stop")
        dog.stop()

    elif command == "STOP_NO_HAND":
        print("DOG COMMAND: stop - no hand")
        dog.stop()

    elif command == "WAIT":
        print("DOG COMMAND: wait")
        dog.stop()

    elif command == "VOICE_MODE":
        print("DOG COMMAND: return to voice mode")
        dog.stop()

    elif command == "SLEEPING":
        print("DOG COMMAND: night / sleeping")
        dog.stop()


def handle_command_transition(dog, stable_command, last_sent_command):
    """
    שולח פקודה לכלב.
    אם יש שינוי בין שתי פקודות תנועה,
    קודם עוצרים לחצי שנייה ורק אז משנים כיוון.
    """

    if stable_command == last_sent_command:
        return last_sent_command

    should_stop_before_change = (
        last_sent_command in MOVEMENT_COMMANDS
        and stable_command in MOVEMENT_COMMANDS
    )

    if should_stop_before_change:
        print("DIRECTION CHANGED: stop before new command")
        dog.stop()
        time.sleep(STOP_BEFORE_DIRECTION_CHANGE_SECONDS)

    send_robot_command(dog, stable_command)
    return stable_command


def draw_zones(frame):
    """
    מצייר קווי עזר על המסך.
    הפונקציה תיקרא רק אם SHOW_CAMERA_WINDOW=True.
    """

    height, width, _ = frame.shape

    left_x = int(width * LEFT_ZONE)
    right_x = int(width * RIGHT_ZONE)

    cv2.line(frame, (left_x, 0), (left_x, height), (255, 255, 255), 2)
    cv2.line(frame, (right_x, 0), (right_x, height), (255, 255, 255), 2)

    cv2.putText(
        frame,
        "LEFT",
        (30, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )

    cv2.putText(
        frame,
        "FORWARD",
        (left_x + 30, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )

    cv2.putText(
        frame,
        "RIGHT",
        (right_x + 30, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )


def check_voice_during_follow(audio_queue, recognizer):
    """
    בודק אם נאמרה פקודת קול בזמן Follow.
    כרגע חשוב לנו בעיקר night.
    לא חוסם את המצלמה.
    """

    if audio_queue is None or recognizer is None:
        return None

    try:
        while not audio_queue.empty():
            data = audio_queue.get_nowait()

            if recognizer.AcceptWaveform(data):
                import json
                text = json.loads(recognizer.Result()).get("text", "").lower()

                if text:
                    print(f"\n[FOLLOW DEBUG] Heard: '{text}'")

                if "night" in text:
                    return "SLEEPING"

    except Exception as error:
        print(f"Voice check during follow error: {error}")

    return None


def draw_debug_window(
    frame,
    raw_gesture,
    open_fingers,
    palm_down,
    raw_command,
    stable_command,
    last_sent_command
):
    """
    מצייר חלון דיבאג רק כשיש DISPLAY.
    אם אין מסך, הפונקציה בכלל לא תיקרא.
    """

    draw_zones(frame)

    cv2.putText(
        frame,
        f"Gesture: {raw_gesture}",
        (20, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Fingers: {open_fingers}",
        (20, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Palm down: {palm_down}",
        (20, 160),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Raw command: {raw_command}",
        (20, 200),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Stable command: {stable_command}",
        (20, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 255, 255),
        2
    )

    cv2.putText(
        frame,
        f"Last sent: {last_sent_command}",
        (20, 280),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 255, 255),
        2
    )

    cv2.putText(
        frame,
        "V SIGN = RETURN TO VOICE MODE",
        (20, 320),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )

    cv2.imshow("XGO Follow Mode", frame)


def run_follow_mode(dog, audio_queue=None, recognizer=None):
    """
    מפעיל מצב Follow.
    מחזיר:
    VOICE_MODE - אם נעשה סימן V
    SLEEPING - אם נאמר night בזמן Follow
    """

    if SHOW_CAMERA_WINDOW:
        print("FOLLOW MODE: camera window enabled")
    else:
        print("FOLLOW MODE: headless mode - no camera window")

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print("Camera not found")
        dog.stop()
        return "VOICE_MODE"

    last_raw_command = None
    raw_command_counter = 0

    stable_command = "STOP_NO_HAND"
    last_sent_command = None

    result_mode = "VOICE_MODE"

    with mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7
    ) as hands:

        try:
            while True:
                #voice_result = check_voice_during_follow(audio_queue, recognizer)

                #if voice_result == "SLEEPING":
                #    print("NIGHT detected during FOLLOW MODE")
                #    result_mode = "SLEEPING"
                #    break

                success, frame = cap.read()

                if not success:
                    print("Failed to read from camera")
                    break

                # מעבד כמו מראה כדי לשמור על אותה לוגיקה של ימין/שמאל
                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                results = hands.process(rgb_frame)

                raw_gesture = "NO_HAND"
                raw_command = "STOP_NO_HAND"
                finger_states = {
                    "thumb": False,
                    "index": False,
                    "middle": False,
                    "ring": False,
                    "pinky": False
                }
                open_fingers = 0
                center_x = None
                center_y = None
                palm_down = False

                if results.multi_hand_landmarks:
                    hand_landmarks = results.multi_hand_landmarks[0]

                    finger_states = get_open_finger_states(hand_landmarks)
                    open_fingers = count_open_fingers_from_states(finger_states)
                    raw_gesture = classify_gesture(finger_states)

                    center_x, center_y = get_hand_center(hand_landmarks)

                    if raw_gesture == "OPEN_HAND":
                        palm_down = is_open_hand_pointing_down(hand_landmarks)

                    raw_command = decide_follow_command(
                        raw_gesture,
                        center_x,
                        hand_landmarks
                    )

                    # ציור ציוני היד רק אם יש חלון
                    if SHOW_CAMERA_WINDOW:
                        mp_draw.draw_landmarks(
                            frame,
                            hand_landmarks,
                            mp_hands.HAND_CONNECTIONS
                        )

                        height, width, _ = frame.shape
                        center_pixel_x = int(center_x * width)
                        center_pixel_y = int(center_y * height)

                        cv2.circle(
                            frame,
                            (center_pixel_x, center_pixel_y),
                            10,
                            (0, 0, 255),
                            -1
                        )

                # ייצוב הפקודה
                if raw_command == last_raw_command:
                    raw_command_counter += 1
                else:
                    last_raw_command = raw_command
                    raw_command_counter = 1

                if raw_command_counter >= STABLE_FRAMES_REQUIRED:
                    stable_command = raw_command

                # שליחת פקודה לכלב עם עצירה לפני שינוי כיוון
                last_sent_command = handle_command_transition(
                    dog,
                    stable_command,
                    last_sent_command
                )

                # אם זוהה סימן V באופן יציב, יוצאים מ-FOLLOW MODE
                if stable_command == "VOICE_MODE":
                    print("EXIT FOLLOW MODE -> RETURN TO VOICE MODE")
                    result_mode = "VOICE_MODE"
                    break

                # תצוגה רק אם יש DISPLAY
                if SHOW_CAMERA_WINDOW:
                    draw_debug_window(
                        frame,
                        raw_gesture,
                        open_fingers,
                        palm_down,
                        raw_command,
                        stable_command,
                        last_sent_command
                    )

                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        result_mode = "VOICE_MODE"
                        break

        except KeyboardInterrupt:
            print("Interrupted by user")
            result_mode = "VOICE_MODE"

        finally:
            print("Stopping dog and closing camera")
            dog.stop()
            cap.release()

            if SHOW_CAMERA_WINDOW:
                cv2.destroyAllWindows()

    return result_mode