#!/usr/bin/python

import asyncio
import time
from huesdk import Hue
from random import randint
import RPi.GPIO as GPIO
import yaml
import os
import vlc
GPIO.setmode(GPIO.BCM)


state = {
    'light_on': False, 
    'button_pressed': False, 
    'coin_inserted': False, 
    'music_playing': False,
    'fog': 0, 
    'fog_request': 0, 
    'quarters': 0
    }

# Load secrets from config file
with open("config.yaml","r") as configfile:
    config = yaml.load(configfile, Loader=yaml.Loader)

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
orig_hls = read_hue(lights)

# Restore a set of lights using a dicts of id->(H,L,S)
def write_hue(lights, id_to_hls):
    # Restore original colors
    for light in lights:
        hls = id_to_hls[light.id_]
        light.set_color(hue=hls[0])  
        light.set_brightness(hls[1])  
        light.set_saturation(hls[2]) 

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

#count = 0
#state = GPIO.input(switch_quarter)
while False:
    print(f"{count}: State is {state}")
    count+=1
    while GPIO.input(switch_quarter)==state:
        continue
    state = GPIO.input(switch_quarter)


# True if a quarter is currently flying through the coin-slot (brief!)
async def see_quarter():
    if GPIO.input(switch_quarter):
        while GPIO.input(switch_quarter):
            await asyncio.sleep(0.1)
        return True
    return False

# Turn on (or off) the laser
def do_laser(on=True):
    GPIO.output(relay_laser, on)

# Turn on (or off) the main white JukeBox lights
def do_lights(on=True):
    GPIO.output(relay_lights, not on)

# Make the lights "cold start" like an old fluorescent
def sputter_lights():
    do_lights()
    time.sleep(0.05)
    do_lights(False)
    time.sleep(0.1)
    do_lights()
    time.sleep(0.15)
    do_lights(False)
    time.sleep(0.2)
    do_lights()

# Run the fog for a short time (or forever? >@_@< )
async def do_fog():
    while True:
        request = state["fog_request"]
        if request:
            print(f"Request for {request} fog")
            state["fog_request"] = 0
        if request > state["fog"]:
            state["fog"] = request
        if state["fog"]:
            print(f"Fog countdown {state['fog']}")
            state["fog"]-=1
            GPIO.output(relay_fog, True)
            await asyncio.sleep(1)
        else:
            GPIO.output(relay_fog, False)
            await asyncio.sleep(1)

async def do_quarter():
    while True:
        qtr = await see_quarter()
        if qtr:
            print(f"{qtr}")
            state["quarters"]+=1
            print(f"See Quarter! {state['quarters']}")
        await asyncio.sleep(0.1)

async def do_statemachine():
    while True:
        if state["quarters"]>0:
            print("Consume Quarter")
            state["quarters"]-=1
            state["fog_request"] =  state["fog"] + 3
        await asyncio.sleep(1)
    
def playpause():
    os.system("qdbus org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause")

sputter_lights()

# Warmup the fog machine
#print("Disabling the Fog machine.  (Break here to keep off).")
#GPIO.output(power_fog, False)
#time.sleep(2)

GPIO.output(power_fog, True)
do_laser()

async def main():
    await asyncio.gather(
        do_fog(),
        do_quarter(),
        do_statemachine(),
    )

asyncio.run(main())


exit(1)

GPIO.output(power_fog, True)
time.sleep(1)
do_fog(10)
do_laser()
GPIO.output(relay_left, False)
GPIO.output(relay_right, False)

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


instance = vlc.Instance("--loop")

# Click Player plays jukebox mechanical button noises
clickplayer = instance.media_player_new()
clickplayer.audio_set_volume(50)
m = instance.media_new("file:///home/jon/Downloads/twoclick.mp3")
clickplayer.set_media(m)

# Music player plays the actual records
musicplayer = instance.media_list_player_new()
#musicplayer.audio_set_volume(100)
musicplayer.get_media_player().audio_set_volume(20)


root = config["music_dir"]
last_button = ''
cl = None
cn = None
while(1):
    button = readTT(button_map)
    if button and button != last_button:
        print(button)
        clickplayer.stop()
        clickplayer.play()
        time.sleep(0.001)
        clickplayer.set_time(520)
        last_button = button
        if button in letters:
            cl = button
        elif button in numbers:
            cn = button
        if cl and cn:
            sel = f"{cl}{cn}"
            print(f"I will play {sel}")
            if sel=="A0":
                do_laser(True)
            elif sel=="B0":
                do_laser(False) 
            elif sel=="C0":
                GPIO.output(power_fog, True)
            elif sel=="D0":
                GPIO.output(power_fog, False)
            elif sel=="E0":
                do_fog(3)
            elif sel=="J0":
                musicplayer.next()
            elif sel=="K0":
                musicplayer.stop()

            elif sel=="H0":
                song = "PaulMcCartney/OdeToAKoalaBear.mp3"
                mediaList = instance.media_list_new()
                m = instance.media_new(f"file://{root}/{song}")
                mediaList.add_media(m)
                musicplayer.stop()
                musicplayer.set_media_list(mediaList)
                musicplayer.play()
                do_fog(3)
                do_laser(True)
            elif sel=="F0":
                song="LilNasX/OldTownRoad.mp3"
                mediaList = instance.media_list_new()
                m = instance.media_new(f"file://{root}/{song}")
                mediaList.add_media(m)
                musicplayer.stop()
                musicplayer.set_media_list(mediaList)
                musicplayer.play()
                do_fog(3)
                do_laser(True)
            elif sel in config["music"]:
                root = config["music_dir"]
                songs = config["music"][sel]
                mediaList = instance.media_list_new()
                if isinstance(songs, list):
                    for song in songs:
                        print(f"Adding song {song}")
                        m = instance.media_new(f"file://{root}/{song}")
                        mediaList.add_media(m)
                else:
                    m = instance.media_new(f"file://{root}/{songs}")
                    mediaList.add_media(m)
                musicplayer.stop()
                musicplayer.set_media_list(mediaList)
                musicplayer.get_media_player().audio_set_volume(1)
                musicplayer.play()
                musicplayer.get_media_player().audio_set_volume(1)
                

            cl = None
            cn = None
    
    
print("Preparing to Warmup Fog")
GPIO.output(power_fog, True)
do_lights(False)
    
    
# Do a mini-show (demo) when a quarter is inserted
while True:
    print("KIDS RULE ADULTS DROOL!!!")
    print("Ready for quarter")
    while not see_quarter():
        continue
    sputter_lights()
    do_fog(3)
    randomize_each_hue(lights)
    do_laser()
    playpause()
    randomize_random_hue(lights)
    time.sleep(60)
    do_laser(False)
    do_lights(False)
    write_hue(lights, orig_hls)

GPIO.cleanup()
exit(0)
