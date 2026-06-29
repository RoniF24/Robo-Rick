import os
import queue
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import xgolib_dog
import sys
import json
import time
from subprocess import Popen, DEVNULL

from follow_mode import run_follow_mode


# =========================================================================
# -------------------- Settings & Angles ----------------------------------
# =========================================================================

WALK_SPEED = 4
ALL_MOTOR_IDS = [11, 12, 13, 21, 22, 23, 31, 32, 33, 41, 42, 43]
SIT_ANGLES = [48.33, 37.51, 1.34, 49.35, 38.75, 0.85, -35.27, 73.05, 1.82, -34.76, 72.42, 1.09]

# משתני סטטוס
is_awake = False
is_moving = False


def print_menu():
    os.system('clear')
    print("============================================")
    print("           XGO ROBOT STATUS: " + ("AWAKE" if is_awake else "SLEEPING"))
    print("============================================")
    if is_awake:
        print("Commands: sit, stand, up, go, walk [1-20],")
        print("          hello, spin, pickle, freeze, night.")
        print("          switch mode / follow mode -> hand follow mode.")
        print("Stop Commands: freeze, stand, up")
    else:
        print("Say 'good morning' to wake up.")
    print("============================================")
    print("Status: Listening...")
    print("--------------------------------------------")


# =========================================================================
# -------------------- Audio ------------------------------------------------
# =========================================================================

audio_queue = queue.Queue()


def audio_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    audio_queue.put(bytes(indata))


def get_seconds_from_text(text):
    numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "fifteen": 15,
        "twenty": 20
    }

    for word, val in numbers.items():
        if word in text:
            return val

    return 3


def clear_audio_queue():
    """
    מנקה שאריות אודיו כדי למנוע פקודות ישנות אחרי מעבר מצב.
    """

    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except Exception:
            break


def go_to_sleep():
    """
    לוגיקת לילה טוב:
    איפוס ואז כיבוי מנועים.
    """

    global is_awake
    global is_moving

    print("-> Good night. Going to sleep.")
    is_awake = False
    is_moving = False

    dog.stop()
    dog.reset()
    time.sleep(0.5)
    dog.unload_allmotor()
    print_menu()


def func_release():
    print("\n[Status: Sitting] Waiting for 'good boy'...")

    while True:
        data = audio_queue.get()

        if recognizer_locked.AcceptWaveform(data):
            text = json.loads(recognizer_locked.Result()).get("text", "").lower()

            if "good boy" in text:
                print("-> Good boy! Standing up.")
                dog.load_allmotor()
                dog.reset()
                dog.action(16)
                break


def execute_pickle():
    print("\n-> [Status: Executing Pickle Rick Scenario]")
    dog.unload_allmotor()

    try:
        proc = Popen(
            ["mplayer", "-ao", "alsa:device=hw=1.0", "-quiet", "pickle.mp3"],
            stdout=DEVNULL,
            stderr=DEVNULL
        )

        while proc.poll() is None:
            time.sleep(0.1)

    except Exception as e:
        print(f"Error: {e}")

    dog.load_allmotor()
    dog.reset()
    print("-> Pickle scenario finished.")


# =========================================================================
# Initialization
# =========================================================================

dog = xgolib_dog.XGO_DOG('/dev/ttyAMA0')
dog.unload_allmotor()

model = Model("model")

main_commands = (
    '["sit", "stand", "up", "go", "walk", "hello", "spin", "pickle", '
    '"freeze", "good morning", "night", '
    '"switch", "mode", "switch mode", "follow", "follow mode", '
    '"one", "two", "three", "four", "five", '
    '"six", "seven", "eight", "nine", "ten", "fifteen", "twenty", "[unk]"]'
)

recognizer = KaldiRecognizer(model, 16000, main_commands)
recognizer_locked = KaldiRecognizer(model, 16000, '["good", "boy", "[unk]"]')

print_menu()


# =========================================================================
# Main Loop
# =========================================================================

try:
    with sd.RawInputStream(
        samplerate=16000,
        blocksize=8000,
        dtype='int16',
        channels=1,
        callback=audio_callback
    ):
        while True:
            data = audio_queue.get()

            if recognizer.AcceptWaveform(data):
                text = json.loads(recognizer.Result()).get("text", "").lower()

                if text:
                    print(f"\n[DEBUG] Heard: '{text}'")

                if not is_awake:
                    if "good morning" in text:
                        is_awake = True
                        dog.load_allmotor()
                        dog.reset()
                        dog.action(14)
                        print_menu()

                else:
                    if "good night" in text:
                        go_to_sleep()

                    elif "switch mode" in text or "follow mode" in text or "follow" in text:
                        print("-> Switching to FOLLOW MODE")
                        dog.stop()
                        clear_audio_queue()

                        follow_result = run_follow_mode(
                            dog,
                            audio_queue=audio_queue,
                            recognizer=recognizer
                        )

                        clear_audio_queue()

                        if follow_result == "SLEEPING":
                            go_to_sleep()

                        else:
                            print("-> Returned to VOICE MODE")
                            dog.stop()
                            print_menu()

                    elif "sit" in text:
                        dog.motor(ALL_MOTOR_IDS, SIT_ANGLES)
                        func_release()

                    elif "pickle" in text:
                        execute_pickle()

                    elif "hello" in text:
                        dog.action(19)
                        time.sleep(3)
                        dog.reset()

                    elif "spin" in text:
                        for _ in range(2):
                            dog.action(4)
                            time.sleep(3)
                        dog.reset()

                    elif "walk" in text:
                        is_moving = True
                        dog.move('x', WALK_SPEED)
                        time.sleep(get_seconds_from_text(text))
                        dog.stop()
                        is_moving = False

                    elif "go" in text:
                        is_moving = True
                        dog.move('x', WALK_SPEED)

                    elif any(cmd in text for cmd in ["freeze", "stand", "up"]):
                        if is_moving:
                            print(f"-> Stopping! Command detected: '{text}'")
                            dog.stop()
                            dog.reset()
                            is_moving = False

                    if is_awake:
                        print_menu()

except KeyboardInterrupt:
    print("\nStopped.")
    dog.stop()