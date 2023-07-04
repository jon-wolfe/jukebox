#!/usr/bin/python

import asyncio
import time
from huesdk import Hue
from random import randint
from playsound import playsound
import RPi.GPIO as GPIO
import yaml
import os
import vlc
GPIO.setmode(GPIO.BCM)



state = {
    'quarter_count': 0,
    'fog_remain_time': 0,
    'light_remain_time': 0,
    'laser_remain_time': 0,
    'light_on': False,
    'laser_on': False,
    'button_list': ['X'],   # Each button pushed to end of list when pressed
    'button_capture': '',  # The last-observed button (no double-count!)
    'button_forget': 0,     # Allow double-count after timeout
    'button_newpress': False,  # Doorbell when a new button is pressed (make a noise, please?)
    'song_list': [],   # Songs selected by human
    'song_bucket': [],  # Backup material for songs selected by human
}

# Load secrets from config file
with open("config.yaml","r") as configfile:
    config = yaml.load(configfile, Loader=yaml.Loader)

#with open("hue_config.yaml","r") as configfile:
#    hue_config = yaml.load(configfile, Loader=yaml.Loader)
hue_config = [0,0,0,0,0,0,0,0,0]

# Connect to our bridge
hue = Hue(bridge_ip=config["hue_ip"], username=config["hue_username"])
lights = hue.get_lights()

# Save all current light colors
# NOTE: This can be inaccurate.  AppleTV maybe doesn't update Hue Bridge?
def read_hue(lights):
    print("Remembering existing light colors")
    old_hls = {}
    for light in lights:
        old_hls[light.id_] = (light.hue, light.bri, light.sat)
    print("  Gathered")
    return old_hls

def read_hue_slot(slot):
    hue_config[slot] = read_hue(lights)

def save_hue_config():
    with open("hue_config.yaml","w") as configfile:
        yaml.safe_dump(hue_config, configfile)

orig_hls = read_hue(lights)

# Restore a set of lights using a dicts of id->(H,L,S)
def write_hue(lights, id_to_hls):
    # Restore original colors
    for light in lights:
        hls = id_to_hls[light.id_]
        light.set_color(hue=hls[0])  
        light.set_brightness(hls[1])  
        light.set_saturation(hls[2]) 

def write_hue_slot(slot):
    write_hue(lights, hue_config[slot])

# These default colors were chosen by my 8yo son to look like minecraft
def randomize_a_hue(light, H=(17000,25000), L=(5,254), S=(254,254)):
    # Set a light to a random color
    light.set_color(hue=randint(*H))
    light.set_brightness(randint(*L))
    light.set_saturation(randint(*S))
    


def randomize_each_hue(lights, H=(17000,25000), L=(5,254), S=(254,254)):
    # Set all lights once to a random color
    for light in lights:
        randomize_a_hue(light, H,L,S)
    
def randomize_random_hue(lights, H=(17000,25000), L=(5,254), S=(254,254), count=100):
    # Find all valid ids
    valid_ids = []
    for light in lights:
        valid_ids.append(light.id_)
        
    # Randomly pick lights and rerfesh
    for i in range(count):
        lightnum = randint(0,len(valid_ids)-1)
        light = hue.get_light(id_=valid_ids[lightnum])
        randomize_a_hue(light, H,L,S)

#############
# Pins for all JukeBox relays, buttons, etc.
relay_right = 19
relay_left = 20
relay_lights = 12
relay_laser = 16
relay_fog = 6
power_fog = 17

switch_quarter = 1

bank_a = 23
bank_b = 22
pull = 0
button_v = 4
button_w = 27
button_x = 21
button_y = 13
button_z = 26

button_map = [
    (button_v, "AB12"),
    (button_w, "CD34"),
    (button_x, "EF56"),
    (button_y, "GH78"),
    (button_z, "JK90")
]
letters = "ABCDEFGHJK"
numbers = "1234567890"
#############
# Setup all inputs and outputs
GPIO.setup(relay_left, GPIO.OUT)
GPIO.setup(relay_right, GPIO.OUT)
GPIO.setup(relay_laser, GPIO.OUT)
GPIO.setup(relay_lights, GPIO.OUT)
GPIO.setup(relay_fog, GPIO.OUT)
GPIO.setup(power_fog, GPIO.OUT)

GPIO.setup(switch_quarter, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# The 20x 0-9 and A-H buttons use a drive/read
#   multiplexing scheme
GPIO.setup(bank_a, GPIO.OUT)
GPIO.setup(bank_b, GPIO.OUT)
GPIO.setup(pull, GPIO.OUT)

GPIO.setup(button_v, GPIO.IN)
GPIO.setup(button_w, GPIO.IN)
GPIO.setup(button_x, GPIO.IN)
GPIO.setup(button_y, GPIO.IN)
GPIO.setup(button_z, GPIO.IN)

# Set everything to nominal
GPIO.output(relay_laser, False)
GPIO.output(relay_lights, True)
GPIO.output(relay_left, False)
GPIO.output(relay_right, False)



###############################################
# Setup VLC media player (for actual music)
###############################################
instance = vlc.Instance("--loop")

# Music player plays the actual records
musicplayer = instance.media_list_player_new()
#musicplayer.audio_set_volume(100)
musicplayer.get_media_player().audio_set_volume(20)

root = config["music_dir"]


# True if a quarter is currently flying through the coin-slot (brief!)
async def see_quarter():
    if GPIO.input(switch_quarter):
        while GPIO.input(switch_quarter):
            await asyncio.sleep(0.1)
        return True
    return False

# Turn on (or off) the laser
def raw_laser(on=True):
    GPIO.output(relay_laser, on)
    state["laser_on"] = on

# Turn on (or off) the main white JukeBox lights
def raw_light(on=True):
    GPIO.output(relay_lights, not on)
    state["light_on"] = on

# Make the lights "cold start" like an old fluorescent
def sputter_light():
    raw_light()
    time.sleep(0.05)
    raw_light(False)
    time.sleep(0.1)
    raw_light()
    time.sleep(0.15)
    raw_light(False)
    time.sleep(0.2)
    raw_light()

# Make the lights "wink" for user-feedback
def wink_light():
    on = state["light_on"]
    raw_light(on=not on)
    time.sleep(0.05)
    raw_light(on=on)

def set_time_fog(time=3):
    if time==0:
        state["fog_remain_time"]=0
    else:
        state["fog_remain_time"]+=time

def is_music_playing():
    return musicplayer.get_state() == vlc.State.Playing

def music_pause():
    vlc_state = musicplayer.get_state()
    if vlc_state == vlc.State.Paused:
        musicplayer.play()
    else:
        musicplayer.pause()

def music_stop():
    musicplayer.stop()

def clear_songlist():
    state["song_list"] = []
    state["song_bucket"] = []

def all_off():
    state["light_remain_time"] = 0
    state["fog_remain_time"] = 0
    state["quaerter_count"] = 0
    state["light_on"] = False
    clear_songlist()
    raw_laser(on=False)
    raw_light(on=False)
    set_time_fog(0)
    music_stop()

def reset_timeout(timeout=60*60):
    state["light_remain_time"] = timeout

specials = {
    "ABC1": [write_hue_slot, {"slot": 1}],
    "ABC2": [write_hue_slot, {"slot": 2}],
    "ABC3": [write_hue_slot, {"slot": 3}],
    "ABC4": [write_hue_slot, {"slot": 4}],
    "ABC5": [write_hue_slot, {"slot": 5}],
    "ABC6": [write_hue_slot, {"slot": 6}],
    "ABC7": [write_hue_slot, {"slot": 7}],
    "ABC8": [write_hue_slot, {"slot": 8}],
    "ABC9": [write_hue_slot, {"slot": 9}],
    "ABD1": [read_hue_slot, {"slot": 1}],
    "ABD2": [read_hue_slot, {"slot": 2}],
    "ABD3": [read_hue_slot, {"slot": 3}],
    "ABD4": [read_hue_slot, {"slot": 4}],
    "ABD5": [read_hue_slot, {"slot": 5}],
    "ABD6": [read_hue_slot, {"slot": 6}],
    "ABD7": [read_hue_slot, {"slot": 7}],
    "ABD8": [read_hue_slot, {"slot": 8}],
    "ABD9": [read_hue_slot, {"slot": 9}],
    "ABD0": [save_hue_config, {}],
    "JK1": [raw_laser, {"on": True}],
    "JK2": [raw_laser, {"on": False}],
    "JK3": [set_time_fog, {"time": 10}],
    "JK4": [set_time_fog, {"time": 0}],
    "JK9": [music_pause, {}],
    "JK0": [music_stop, {}],
    "HJK0": [all_off, {}],
}

def clicky_noise():
    playsound("./RelayClick.mp3", False)

def readTT(button_map):
    # A group of four buttons is read off one wire
    #   by controlling the voltage of BankA and BankB,
    #   adjusting a weak-pull up/down,
    #   and reading the resulting level from the sense pin.
    # The four tests below test for each button of a group.
    # Each test is (BankA, BankB, Pull, ActiveHigh)
    tests = [(True,False,False,False),  # "A" (active low)
             (False,True,True,True),    # "B" (active high)
             (False,True,False,False),  # "1" (active low)
             (True,False,True,True),]   # "2" (active high)
    results = []
    for test in tests:
        (ba,bb,p,inv) = test
        GPIO.output(bank_a, ba)
        GPIO.output(bank_b, bb)
        GPIO.output(pull, p)
        time.sleep(0.001)
        for (button_group, _) in button_map:
            results.append(GPIO.input(button_group) ^ inv)
    letter_order = ""
    for i in range(4):
        for (_, letters) in button_map:
            letter_order += letters[i]
    pressed = [letter for (letter,result) in zip(letter_order,results) if result]
    return "".join(pressed)


async def loop_button():
    period = 0.05
    while True:
        await asyncio.sleep(period)
        if not state["light_on"]:
            # No button-read in OFF-state
            continue
        current = readTT(button_map)
        if current and current != state["button_capture"]:
            clicky_noise()
            wink_light()
            state["button_newpress"] = True
        if current:
            state["button_forget"] = 3
            state["button_capture"] = current
        if current and state["button_list"][-1] != current:
            state["button_list"].append(current)
        if state["button_forget"] > 0:
            state["button_forget"]-=period
        else:
            state["button_capture"] = ''


# Run the fog for a short time (or forever? >@_@< )
async def loop_fog():
    while True:
        if state["fog_remain_time"]:
            print(f"Fog countdown {state['fog_remain_time']}")
            state["fog_remain_time"]-=1
            GPIO.output(relay_fog, True)
            await asyncio.sleep(1)
        else:
            GPIO.output(relay_fog, False)
            await asyncio.sleep(1)

async def loop_light():
    while True:
        if state["light_remain_time"]:
#            print(f"Light countdown {state['light_remain_time']}")
            state["light_remain_time"]-=1
            if not state["light_on"]:
                sputter_light()
                state["light_on"] = True
            await asyncio.sleep(1)
        else:
            clear_songlist()
            if not is_music_playing():
                all_off()
            await asyncio.sleep(1)

async def loop_quarter():
    while True:
        qtr = await see_quarter()
        if qtr:
            reset_timeout()
            print(f"{qtr}")
            state["quarter_count"]+=1
            print(f"See Quarter! {state['quarter_count']}")
        await asyncio.sleep(0.1)

async def loop_songplay():
    while True:
        await asyncio.sleep(1)
        vlc_state = musicplayer.get_state()
        if vlc_state == vlc.State.Playing:
            continue
        if vlc_state not in [
            vlc.State.Playing,
            vlc.State.Paused,
            vlc.State.Stopped,
            vlc.State.NothingSpecial,
            vlc.State.Ended,
        ]:
            print(f"VLC UNKNOWN STATE: {vlc_state}")

        # Play the next song in the song_list
        if len(state["song_list"]):
            next_song = state["song_list"][0]
            state["song_list"] = state["song_list"][1:]
            mediaList = instance.media_list_new()
            m = instance.media_new(next_song)
            mediaList.add_media(m)
            musicplayer.stop()
            musicplayer.set_media_list(mediaList)
            musicplayer.get_media_player().audio_set_volume(1)
            musicplayer.play()
            musicplayer.get_media_player().audio_set_volume(1)
            continue

        # If no explicit pick, play recent bonus-songs
        if len(state["song_bucket"]):
            next_song = state["song_bucket"][-1]
            state["song_bucket"] = state["song_bucket"][0:-1]
            mediaList = instance.media_list_new()
            m = instance.media_new(next_song)
            mediaList.add_media(m)
            musicplayer.stop()
            musicplayer.set_media_list(mediaList)
            musicplayer.get_media_player().audio_set_volume(1)
            musicplayer.play()
            musicplayer.get_media_player().audio_set_volume(1)


def add_song(pair):
    if pair in config["music"]:
        root = config["music_dir"]
        songs = config["music"][pair]
        if isinstance(songs, list):
            if len(songs):
                song_name = f"file://{root}/{songs[0]}"
                if song_name in state["song_list"]:
                    print("Skipping would-be-dupe")
                    return
                state["song_list"].append(song_name)
            if len(songs)>1:
                for song in songs[1:]:
                    state["song_bucket"].append(f"file://{root}/{song}")
        else:
            song_name = f"file://{root}/{songs}"
            if song_name in state["song_list"]:
                print("Skipping would-be-dupe")
            state["song_list"].append(song_name)
    else:
        print(f"DEBUG: No song for selection {pair}")

# Return True if any special was found, else return False
def execute_buttons(buttons):
#    print(f"Buttons are: {buttons}")
    for length in [4,3]:
        if len(buttons)<length:
            continue
        end = buttons[-length:]
        if end in specials:
            specials[end][0](**specials[end][1])
            return True
    if len(buttons)>=2:
        end = buttons[-2:]
        if end[0] in "ABCDEFGHJK" and end[1] in "0123456789":
            add_song(end)
            return True
        
    return False

async def loop_statemachine():
    while True:
        await asyncio.sleep(1)
        if state["quarter_count"]>0:
            print("Consume Quarter")
            state["quarter_count"]-=1
            state["fog_remain_time"] =  state["fog_remain_time"] + 3
            reset_timeout()
        if not state["light_on"]:
            # Put in a quarter if you want music, etc!
            continue
        buttons = "".join(state["button_list"])
        if execute_buttons(buttons):
            state["button_list"] = ["X"]

sputter_light()

# Warmup the fog machine
#print("Disabling the Fog machine.  (Break here to keep off).")
#GPIO.output(power_fog, False)
#time.sleep(2)

GPIO.output(power_fog, True)

async def main():
    await asyncio.gather(
        loop_light(),
        loop_fog(),
        loop_quarter(),
        loop_statemachine(),
        loop_button(),
        loop_songplay(),
    )

asyncio.run(main())


exit(1)

    
print("Preparing to Warmup Fog")
GPIO.output(power_fog, True)
raw_light(False)
    
    
# Do a mini-show (demo) when a quarter is inserted
while True:
    print("KIDS RULE ADULTS DROOL!!!")
    print("Ready for quarter")
    while not see_quarter():
        continue
    sputter_light()
    do_fog(3)
    randomize_each_hue(lights)
    raw_laser()
    playpause()
    randomize_random_hue(lights)
    time.sleep(60)
    raw_laser(False)
    raw_light(False)
    write_hue(lights, orig_hls)

GPIO.cleanup()
exit(0)
