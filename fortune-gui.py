#!/usr/bin/env python3
import asyncio
import os
import random
import argparse

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from datetime import datetime

import PIL.Image
import PIL.ImageFont
import PIL.ImageDraw
import PIL.ImageChops
import PIL.ImageTk

# CRC8 table extracted from APK, pretty standard though
crc8_table = (
    0x00, 0x07, 0x0e, 0x09, 0x1c, 0x1b, 0x12, 0x15, 0x38, 0x3f, 0x36, 0x31,
    0x24, 0x23, 0x2a, 0x2d, 0x70, 0x77, 0x7e, 0x79, 0x6c, 0x6b, 0x62, 0x65,
    0x48, 0x4f, 0x46, 0x41, 0x54, 0x53, 0x5a, 0x5d, 0xe0, 0xe7, 0xee, 0xe9,
    0xfc, 0xfb, 0xf2, 0xf5, 0xd8, 0xdf, 0xd6, 0xd1, 0xc4, 0xc3, 0xca, 0xcd,
    0x90, 0x97, 0x9e, 0x99, 0x8c, 0x8b, 0x82, 0x85, 0xa8, 0xaf, 0xa6, 0xa1,
    0xb4, 0xb3, 0xba, 0xbd, 0xc7, 0xc0, 0xc9, 0xce, 0xdb, 0xdc, 0xd5, 0xd2,
    0xff, 0xf8, 0xf1, 0xf6, 0xe3, 0xe4, 0xed, 0xea, 0xb7, 0xb0, 0xb9, 0xbe,
    0xab, 0xac, 0xa5, 0xa2, 0x8f, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9d, 0x9a,
    0x27, 0x20, 0x29, 0x2e, 0x3b, 0x3c, 0x35, 0x32, 0x1f, 0x18, 0x11, 0x16,
    0x03, 0x04, 0x0d, 0x0a, 0x57, 0x50, 0x59, 0x5e, 0x4b, 0x4c, 0x45, 0x42,
    0x6f, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7d, 0x7a, 0x89, 0x8e, 0x87, 0x80,
    0x95, 0x92, 0x9b, 0x9c, 0xb1, 0xb6, 0xbf, 0xb8, 0xad, 0xaa, 0xa3, 0xa4,
    0xf9, 0xfe, 0xf7, 0xf0, 0xe5, 0xe2, 0xeb, 0xec, 0xc1, 0xc6, 0xcf, 0xc8,
    0xdd, 0xda, 0xd3, 0xd4, 0x69, 0x6e, 0x67, 0x60, 0x75, 0x72, 0x7b, 0x7c,
    0x51, 0x56, 0x5f, 0x58, 0x4d, 0x4a, 0x43, 0x44, 0x19, 0x1e, 0x17, 0x10,
    0x05, 0x02, 0x0b, 0x0c, 0x21, 0x26, 0x2f, 0x28, 0x3d, 0x3a, 0x33, 0x34,
    0x4e, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5c, 0x5b, 0x76, 0x71, 0x78, 0x7f,
    0x6a, 0x6d, 0x64, 0x63, 0x3e, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2c, 0x2b,
    0x06, 0x01, 0x08, 0x0f, 0x1a, 0x1d, 0x14, 0x13, 0xae, 0xa9, 0xa0, 0xa7,
    0xb2, 0xb5, 0xbc, 0xbb, 0x96, 0x91, 0x98, 0x9f, 0x8a, 0x8d, 0x84, 0x83,
    0xde, 0xd9, 0xd0, 0xd7, 0xc2, 0xc5, 0xcc, 0xcb, 0xe6, 0xe1, 0xe8, 0xef,
    0xfa, 0xfd, 0xf4, 0xf3
)


def crc8(data):
    crc = 0
    for byte in data:
        crc = crc8_table[(crc ^ byte) & 0xFF]
    return crc & 0xFF


# General message format:
# Magic number: 2 bytes 0x51, 0x78
# Command: 1 byte
# 0x00
# Data length: 1 byte
# 0x00
# Data: Data Length bytes
# CRC8 of Data: 1 byte
# 0xFF
def format_message(command, data):
    data = [0x51, 0x78] + [command] + [0x00] + [len(data)] + [0x00] + data + [crc8(data)] + [0xFF]
    return data


def printer_short(i):
    return [i & 0xFF, (i >> 8) & 0xFF]


# Commands
RetractPaper = 0xA0  # Data: Number of steps to go back
FeedPaper = 0xA1  # Data: Number of steps to go forward
DrawBitmap = 0xA2  # Data: Line to draw. 0 bit -> don't draw pixel, 1 bit -> draw pixel
GetDevState = 0xA3  # Data: 0
ControlLattice = 0xA6  # Data: Eleven bytes, all constants. One set used before printing, one after.
GetDevInfo = 0xA8  # Data: 0
OtherFeedPaper = 0xBD  # Data: one byte, set to a device-specific "Speed" value before printing
#                              and to 0x19 before feeding blank paper
DrawingMode = 0xBE  # Data: 1 for Text, 0 for Images
SetEnergy = 0xAF  # Data: 1 - 0xFFFF
SetQuality = 0xA4  # Data: 0x31 - 0x35. APK always sets 0x33 for GB01
UpdateDevice = 0xA9 

PrintLattice = [0xAA, 0x55, 0x17, 0x38, 0x44, 0x5F, 0x5F, 0x5F, 0x44, 0x38, 0x2C]
FinishLattice = [0xAA, 0x55, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x17]
XOff = (0x51, 0x78, 0xAE, 0x01, 0x01, 0x00, 0x10, 0x70, 0xFF)
XOn = (0x51, 0x78, 0xAE, 0x01, 0x01, 0x00, 0x00, 0x00, 0xFF)

max_energy = 0xFFFF
max_energy_bytes = [ max_energy.to_bytes(2, 'little')[0], max_energy.to_bytes(2, 'little')[1]]

energy = {
    0: printer_short(8000),
    1: printer_short(12000),
    # 2: printer_short(17500)
    2: max_energy_bytes
}
contrast = 2

# PrinterWidth = 384
PrinterWidth = 384

ImgPrintSpeed = [0x01]
BlankSpeed = [0x19]

feed_lines = 80
header_lines = 0
scale_feed = False

packet_length = 60 
throttle = 0.01

address = None
PrinterCharacteristic = "0000AE01-0000-1000-8000-00805F9B34FB"
NotifyCharacteristic = "0000AE02-0000-1000-8000-00805F9B34FB"
device = None
fixed_index = None

# show notification data
debug = False

def detect_printer(detected, advertisement_data):
    global device
    if debug:
        print(detected.name)
    if address:
        cut_addr = detected.address.replace(":", "")[-(len(address)):].upper()
        if cut_addr != address:
            return
    if detected.name == 'MX06':
        device = detected


def notification_handler(sender, data):
    global debug
    if debug:
        print("{0}: [ {1} ]".format(sender, " ".join("{:02X}".format(x) for x in data)))
    if tuple(data) == XOff:
        print("ERROR: printer data overrun!")
        return
    if data[2] == GetDevState:
        if data[6] & 0b1000:
            print("warning: low battery! print quality might be affected…")
        # print("printer status byte: {:08b}".format(data[6]))
        # xxxxxxx1 no_paper ("No paper.")
        # xxxxxx10 paper_positions_open ("Warehouse.")
        # xxxxx100 too_hot ("Too hot, please let me take a break.")
        # xxxx1000 no_power_please_charge ("I have no electricity, please charge")
        # I don't know if multiple status bits can be on at once, but if they are, then iPrint won't detect them.
        # In any case, I think the low battery flag is the only one the GB01 uses.
        # It also turns out this flag might not turn on, even when the battery's so low the printer shuts itself off…
        return


async def connect_device():
    scanner = BleakScanner(detection_callback=detect_printer)
    await scanner.start()
    for x in range(200):
        await asyncio.sleep(0.1)
        if device:
            print("Printer connected.")
            break
    await scanner.stop()

async def connect_and_send(data):
    if not device:
        scanner = BleakScanner(detection_callback=detect_printer)
        await scanner.start()
        for x in range(200):
            await asyncio.sleep(0.1)
            if device:
                print("Printer connected.")
                break
        await scanner.stop()

    if not device:
        print("The printer could not be found :(")
        return
    async with BleakClient(device) as client:
        # Set up callback to handle messages from the printer
        await client.start_notify(NotifyCharacteristic, notification_handler)

        while data:
            # Cut the command stream up into pieces small enough for the printer to handle
            await client.write_gatt_char(PrinterCharacteristic, bytearray(data[:packet_length]))
            data = data[packet_length:]
            if throttle is not None:
                await asyncio.sleep(throttle)

def request_status():
    return format_message(GetDevState, [0x00])

def to_unsigned_byte(val):
    '''Converts a byte in signed representation to unsigned. Assumes val is encoded in two's
    complement.'''
    return val if val >= 0 else val & 0xff

def bs(lst):
    '''This is an utility function that transforms a list of unsigned bytes (in two's complement)
    into an unsigned bytearray.

    The reason it exists is that in Java (where these commands were reverse engineered from), bytes
    are signed. Instead of manually converting them, let the computer do it for us, so it's easier
    to debug and extend it with new reverse engineered commands.
    '''
    return bytearray(map(to_unsigned_byte, lst))


CMD_GET_DEV_STATE = bs([
    81, 120, -93, 0, 1, 0, 0, 0, -1
])

CMD_SET_QUALITY_200_DPI = bs([81, 120, -92, 0, 1, 0, 50, -98, -1])

def blank_paper(lines):
    # Feed extra paper for image to be visible
    blank_commands = format_message(OtherFeedPaper, BlankSpeed)
    count = lines
    while count:
        feed = min(count, 0xFF)
        blank_commands = blank_commands + format_message(FeedPaper, printer_short(feed))
        count = count - feed
    return blank_commands

def get_wrapped_text(text: str, font: PIL.ImageFont.ImageFont,
                     line_length: int):
    if font.getlength(text) <= line_length:
        return text

    lines = ['']
    for word in text.split():
        line = f'{lines[-1]} {word}'.strip()
        if font.getlength(line) <= line_length:
            lines[-1] = line
        else:
            lines.append(word)
    return '\n'.join(lines)

def trim(im):
    bg = PIL.Image.new(im.mode, im.size, (255,255,255))
    diff = PIL.ImageChops.difference(im, bg)
    diff = PIL.ImageChops.add(diff, diff, 2.0)
    bbox = diff.getbbox()
    if bbox:
        return im.crop((bbox[0],bbox[1],bbox[2],bbox[3]+10)) # don't cut off the end of the image

def create_text(text, font_name="thermal-receipt.otf", font_size=30):
    img = PIL.Image.new('RGB', (PrinterWidth, 50), color = (255, 255, 255))
    font = PIL.ImageFont.truetype(font_name, font_size)
    
    d = PIL.ImageDraw.Draw(img)
    lines = []
    for line in text.splitlines():
        lines.append(get_wrapped_text(line, font, PrinterWidth))
    lines = "\n".join(lines)
    d.text((40,12), lines, fill=(0,0,0), font=font)
    return img

quality1 = [0x51, 0x78, 0xA4, 0x00, 0x01, 0x00, 0x32, 0x9e, 0xFF]
quality5 = [0x51, 0x78, 0xA4, 0x00, 0x01, 0x00, 0x35, 0x8B, 0xFF]
printImage = [0x51, 0x78, 0xbe, 0x0, 0x1, 0x0, 0x0, 0x0, 0xff]
printEnergy = [0x51, 0x78, 0xAF, 0x00, 0x02, 0x00, 0x28, 0x23, 0xEF, 0xFF]
printSpeed = [0x51, 0x78, 0xbd, 0x00, 0x01, 0x00, 25 & 0xff, 0, 0xff]

def render_image(img):
    global header_lines
    global feed_lines

    cmdqueue = []
    cmdqueue += quality5
    # energy
    cmdqueue += printEnergy
    # cmdqueue += format_message(SetEnergy, [0xff, 0xff])
    # cmdqueue += format_message(SetEnergy, printer_short(20000))
    # cmdqueue += format_message(UpdateDevice, [0])
    cmdqueue += format_message(DrawingMode, [0])
    # cmdqueue += format_message(OtherFeedPaper, [80])
    cmdqueue += printSpeed

    # print model
    # cmdqueue += printImage
    # print speed

    # Set quality to standard
    #  quality 5 = {81, 120, -92, 0, 1, 0, 53, -117, -1}
    
    # speed
    # Set energy used
    # Set mode to image mode / apply energy?
    cmdqueue += format_message(ControlLattice, PrintLattice)

    if img.width > PrinterWidth:
        if debug:
            print("larger", img.width)
        # image is wider than printer resolution; scale it down proportionately
        scale = PrinterWidth / img.width
        if scale_feed:
            header_lines = int(header_lines * scale)
            feed_lines = int(feed_lines * scale)
        img = img.resize((PrinterWidth, int(img.height * scale)))
    if img.width < PrinterWidth:
        if debug:
            print("smaller", img.width)
        # scale up to largest whole multiple
        scale = PrinterWidth // img.width
        if scale_feed:
            header_lines = int(header_lines * scale)
            feed_lines = int(feed_lines * scale)
        img = img.resize((img.width * scale, img.height * scale), resample=PIL.Image.NEAREST)
    # convert image to black-and-white 1bpp color format

    img = img.convert("1")
    if img.width < PrinterWidth:
        if debug:
            print("doing something here")
        # image is narrower than printer resolution
        # pad it out with white pixels
        pad_amount = (PrinterWidth - img.width)
        padded_image = PIL.Image.new("1", (PrinterWidth, img.height), 1)
        padded_image.paste(img, box=(0, pad_amount))
        img = padded_image

    if header_lines:
        cmdqueue += blank_paper(header_lines)

    for y in range(0, img.height):
        bmp = []
        bit = 0
        # pack image data into 8 pixels per byte
        for x in range(0, img.width):
            if bit % 8 == 0:
                bmp += [0x00]
            bmp[int(bit / 8)] >>= 1
            if not img.getpixel((x, y)):
                bmp[int(bit / 8)] |= 0x80
            else:
                bmp[int(bit / 8)] |= 0

            bit += 1

        cmdqueue += format_message(DrawBitmap, bmp)

    # print speed
    # dpi
    # finish the lattice, whatever that means
    cmdqueue += format_message(ControlLattice, FinishLattice)

    return cmdqueue

fortune_dict = {
  "bad": "bad-fortune.png", # 0
  "not-great": "not-great-fortune.png", # 10s
  "below-average": "below-average-fortune.png", # 20s
  "average": "average-fortune.png", # 30s+40s
  "above-average": "above-average-fortune.png", # 50s+60s
  "great": "great-fortune.png", # 70s+80s
  "spectacular": "spectacular-fortune.png", # 90s
}

def fortune_greet():
    print("WELCOME TO THE FORTUNE MACHINE")
    print("How may I help you?")
    print("1. Get fortune")
    print("2. Reconnect printer")
    print("3. Get a specific fortune")
    print("4. Quit")

async def fortune_print():
    # Get time
    now = datetime.now()
    dt_string = now.strftime("%m/%d/%Y %I:%M:%S %p")
    date_img = create_text(dt_string)

    # Get dog of fate
    directory_path = 'dogs'
    file_list = os.listdir(directory_path)
    file_list.sort()
    indices = [index for index, element in enumerate(file_list)]
    random_index = random.choice(indices)
    if debug:
        print(file_list)
    if fixed_index and fixed_index >= 0 and fixed_index < 100:
        random_index = fixed_index
        if debug:
            print("setting to fixed index:", fixed_index)
    if debug:
        print(f"The randomly chosen file is: {file_list[random_index]}, {random_index}")
    dog_img_path = f"dogs/{file_list[random_index]}"

    # Get fortune
    fortune_name = fortune_dict["average"]
    if random_index == 0:
        fortune_name = fortune_dict["bad"]
    elif random_index < 10:
        fortune_name = fortune_dict["not-great"] # 000
    elif random_index < 20:
        fortune_name = fortune_dict["below-average"] # bbb
    elif random_index < 50:
        fortune_name = fortune_dict["average"]
    elif random_index < 70:
        fortune_name = fortune_dict["above-average"] # ggg
    elif random_index < 90:
        fortune_name = fortune_dict["great"] # iii
    elif random_index < 100:
        fortune_name = fortune_dict["spectacular"] # zzz
    fortune_path = f"fortunes/{fortune_name}"


    if random_index == 0:
        await print_bad_fortune(date_img, fortune_path)
    elif random_index >= 90 and random_index <100:
        await print_spectacular_fortune(file_list, date_img, fortune_path)
    else:
        await print_normal_fortune(date_img, dog_img_path, fortune_path)


async def print_bad_fortune(date_img, fortune_path):
    print_data = request_status()
    image1 = PIL.Image.open(fortune_path)
    print_data = print_data + render_image(date_img) + render_image(image1) +  blank_paper(feed_lines)
    await connect_and_send(print_data)

async def print_spectacular_fortune(file_list, date_img, fortune_path):
    print_data = request_status()
    random_numbers = random.sample(range(90, 100), 2)
    dog0 = f"dogs/{file_list[random_numbers[0]]}"
    dog1 = f"dogs/{file_list[random_numbers[1]]}"
    image1 = PIL.Image.open(dog0)
    image2 = PIL.Image.open(dog1)
    image3 = PIL.Image.open(fortune_path)
    print_data += render_image(date_img)
    print_data += render_image(image1)
    await connect_and_send(print_data)
    await asyncio.sleep(5)

    print_data = request_status()
    print_data += render_image(image2)
    print_data += render_image(image3)
    print_data += blank_paper(feed_lines)
    await connect_and_send(print_data)

async def print_normal_fortune(date_img, dog_img_path, fortune_path):
    print_data = request_status()
    image1 = PIL.Image.open(dog_img_path)
    image2 = PIL.Image.open(fortune_path)
    print_data = print_data + render_image(date_img) + render_image(image1) + render_image(image2) +  blank_paper(feed_lines)
    await connect_and_send(print_data)

async def cleanse_print():
    print_data = request_status()
    now = datetime.now()
    dt_string = now.strftime("%d/%m/%Y %I:%M:%S %p")
    text = create_text(dt_string)
    image1 = PIL.Image.open("fortunes/fortune-cleanse.png")
    image2 = PIL.Image.open("fortunes/good-luck-reset.png")
    print_data = print_data + render_image(text) + render_image(image1) + render_image(image2) +  blank_paper(feed_lines)
    await connect_and_send(print_data)

parser = argparse.ArgumentParser(
    description="Prints a given image to a GB01 thermal printer.")
parser.add_argument("-D", "--debug",
                    help="output notifications received from printer, in hex",
                    action="store_true")
parser.add_argument("-i", "--index", type=int, default=None, metavar="INDEX",
                    help="set the specific index to use (0-100)")

args = parser.parse_args()
debug = args.debug
if args.index:
    fixed_index = args.index

from tkinter import *
from tkinter import ttk


import tkinter as tk
from tkinter import PhotoImage
from tkinter import font as tkFont


# Function to handle button click
def start_task_on_thread(background_task):
    async def run_task_and_enable_button(background_task):
        await background_task()
        button1.config(state="normal")
        button2.config(state="normal")

    button1.config(state="disabled")
    button2.config(state="disabled")

    asyncio.create_task(run_task_and_enable_button(background_task))

# Wrapper to run the task and re-enable the button after completion

def on_get_fortune():
    print("get fortune")
    start_task_on_thread(fortune_print)
    print("finished")

def on_cleanse():
    print("get cleanse")
    start_task_on_thread(cleanse_print)

def on_quit():
    print("quit")
    exit();


# Create the main window
root = tk.Tk()
root.title("Image and Buttons Layout")

SCREEN_WIDTH=root.winfo_screenwidth()
SCREEN_HEIGHT=root.winfo_screenheight()
dims = f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}+0+0"

root.geometry(dims)  # Set window size

# Load an image
# Ensure you have a suitable image file
image_path = "dogs/eee-17.jpg"  # Replace with your image path
photo = PIL.Image.open(image_path)
half_width = int(SCREEN_WIDTH/2)
photo = photo.resize((half_width, SCREEN_HEIGHT), PIL.Image.LANCZOS)
photo = photo.convert('1', dither=PIL.Image.FLOYDSTEINBERG)

image = PIL.ImageTk.PhotoImage(photo)

helv36 = tkFont.Font(family='Helvetica', size=36, weight='bold')


# Create a frame for the image
image_frame = tk.Frame(root, width=half_width, height=SCREEN_HEIGHT)
image_frame.pack(side=tk.LEFT, fill=tk.BOTH)

# Create a label to display the image
image_label = tk.Label(image_frame, image=image)
image_label.pack(fill=tk.BOTH, expand=True)

# Create a frame for the buttons
button_frame = tk.Frame(root, width=half_width, height=SCREEN_HEIGHT)
button_frame.pack(side=tk.LEFT, fill=tk.BOTH)

# Create buttons 1/5 of the screen
button_height = SCREEN_HEIGHT // 5
button_width = half_width - 5

# Create three buttons and use place to center them vertically
button1 = tk.Button(button_frame, text="GET FORTUNE", command=lambda: root.after(0, on_get_fortune), font=helv36)
button1.place(relx=0, rely=0.2, width=button_width, height=button_height)

button2 = tk.Button(button_frame, text="Cleanse", command=lambda: root.after(0, on_cleanse), font=helv36)
button2.place(relx=0, rely=0.4, width=button_width, height=button_height)

button3 = tk.Button(button_frame, text="Quit", command=on_quit, font=helv36)
button3.place(relx=0, rely=0.6, width=button_width, height=button_height)

async def main():
    while True:
        root.update()  # Process Tkinter events
        await asyncio.sleep(0.01)  # Pause to yield control to the event loop

# Start the asyncio event loop
asyncio.run(main())



#     fortune_greet()
#     word = input("> ").lower()
#     if word == "1" or word == "fortune":
#         print("Certainly. Fortune printing.")
#         fortune_print()
#     elif word == "2" or word == "reconnect printer":
#         device = None
#         print("Certainly. Reconnecting...")
#         loop = asyncio.get_event_loop()
#         loop.run_until_complete(connect_device())
#     elif word == "3" or word == "get specific fortune":
#         print("Certainly. Please enter a number between 0 and 99:")
#         fixed_input = int(input("> "))
#         if fixed_input and fixed_input >= 0 and fixed_input < 100:
#             fixed_index = fixed_input
#             fortune_print()
#             fixed_index = None
#         else:
#             print("Invalid input, not printing fortune")
#     elif word == "4" or word == "quit":
#         break
#     elif word == "99" or word == "cleanse":
#         print("Right away!!!!")
#         cleanse_print()
#     else:
#         print("I'm sorry, I didn't understand that.")
#     print()

