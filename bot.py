import io
import logging
import os
import random
import string
import zipfile
from datetime import date, timedelta

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)
from PIL import Image, ImageEnhance
from PIL.ExifTags import TAGS
import piexif
import numpy as np
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ── states ────────────────────────────────────────────────────────────────────
STATE_IDLE       = "idle"
STATE_COLLECTING = "collecting"
STATE_WAITING    = "waiting_count"
STATE_PROCESSING = "processing"

# ── fake camera pool ──────────────────────────────────────────────────────────
# Each entry fully describes a real device: optics, firmware, timezone, OS.
# Values are physically accurate (focal lengths, APEX aperture, 35mm equiv).
CAMERAS = [
    # ── Samsung (20) ─────────────────────────────────────────────────────────
    {"make": b"Samsung", "model": b"SM-S928B",  "software": b"S928BXXU2AXD1",
     "host": b"Android 14", "lens_make": b"Samsung", "lens_model": b"Wide Angle 6.4mm f/1.8",
     "focal_mm": (64, 10),  "focal_35mm": 23, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-G991B",  "software": b"G991BXXU5CVC3",
     "host": b"Android 13", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.2mm f/1.8",
     "focal_mm": (62, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-S918B",  "software": b"S918BXXU5AXC1",
     "host": b"Android 14", "lens_make": b"Samsung", "lens_model": b"Wide Angle 6.4mm f/1.7",
     "focal_mm": (64, 10),  "focal_35mm": 23, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-A546B",  "software": b"A546BXXU4AXD5",
     "host": b"Android 14", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-G996B",  "software": b"G996BXXU5CVC3",
     "host": b"Android 13", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.5mm f/1.8",
     "focal_mm": (65, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-S901B",  "software": b"S901BXXU4CWD1",
     "host": b"Android 14", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.6mm f/1.8",
     "focal_mm": (66, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-A235F",  "software": b"A235FXXU2AWF1",
     "host": b"Android 13", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.4mm f/1.8",
     "focal_mm": (64, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-S908B",  "software": b"S908BXXU4CWD1",
     "host": b"Android 14", "lens_make": b"Samsung", "lens_model": b"Wide Angle 6.5mm f/1.8",
     "focal_mm": (65, 10),  "focal_35mm": 23, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-G780G",  "software": b"G780GXXU5FWC1",
     "host": b"Android 13", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-A536B",  "software": b"A536BXXU5CXC3",
     "host": b"Android 13", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.2mm f/1.8",
     "focal_mm": (62, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-S711B",  "software": b"S711BXXU2AXC2",
     "host": b"Android 14", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.2mm f/1.8",
     "focal_mm": (62, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-A135F",  "software": b"A135FXXU4BWF1",
     "host": b"Android 12", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-F946B",  "software": b"F946BXXU3BXC2",
     "host": b"Android 14", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.5mm f/1.8",
     "focal_mm": (65, 10),  "focal_35mm": 23, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-F731B",  "software": b"F731BXXU2CXC1",
     "host": b"Android 14", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.1mm f/1.8",
     "focal_mm": (61, 10),  "focal_35mm": 24, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-G986B",  "software": b"G986BXXU5FVE1",
     "host": b"Android 13", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-G988B",  "software": b"G988BXXU5FWC1",
     "host": b"Android 12", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.5mm f/1.8",
     "focal_mm": (65, 10),  "focal_35mm": 23, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-A525F",  "software": b"A525FXXU6DWC1",
     "host": b"Android 13", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-A736B",  "software": b"A736BXXU4CXD3",
     "host": b"Android 13", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-M536B",  "software": b"M536BXXU4CXC1",
     "host": b"Android 13", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.5mm f/1.8",
     "focal_mm": (65, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Samsung", "model": b"SM-S926B",  "software": b"S926BXXU2AXD1",
     "host": b"Android 14", "lens_make": b"Samsung", "lens_model": b"Main Camera 6.3mm f/1.8",
     "focal_mm": (63, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},

    # ── Xiaomi / Redmi / POCO (18) ────────────────────────────────────────────
    {"make": b"Xiaomi", "model": b"2311DRK48G",  "software": b"OS1.0.4.0.UNACNXM",
     "host": b"Android 14", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.5mm f/1.6",
     "focal_mm": (65, 10),  "focal_35mm": 24, "f_number": (16, 10), "aperture_apex": (136, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"23049PCD8G",  "software": b"MIUI.V816.0.5.0.UMCCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 7.5mm f/1.9",
     "focal_mm": (75, 10),  "focal_35mm": 23, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"22071212AG",  "software": b"MIUI.V140.0.6.0.SLBCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 7.5mm f/1.9",
     "focal_mm": (75, 10),  "focal_35mm": 23, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"22111317G",   "software": b"MIUI.V816.0.3.0.SMHCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.5mm f/1.6",
     "focal_mm": (65, 10),  "focal_35mm": 24, "f_number": (16, 10), "aperture_apex": (136, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"23049RAD8C",  "software": b"MIUI.V816.0.2.0.SMHCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.3mm f/1.8",
     "focal_mm": (63, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"22101320G",   "software": b"MIUI.V140.0.7.0.SLBCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.4mm f/1.7",
     "focal_mm": (64, 10),  "focal_35mm": 23, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"22126RN91Y",  "software": b"MIUI.V140.0.5.0.SLBCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.0mm f/1.9",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"22111317PI",  "software": b"MIUI.V140.0.4.0.SLBCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.2mm f/1.8",
     "focal_mm": (62, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"23013RK75C",  "software": b"OS1.0.3.0.UMKCNXM",
     "host": b"Android 14", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 7.5mm f/1.9",
     "focal_mm": (75, 10),  "focal_35mm": 23, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"2207122MC",   "software": b"MIUI.V130.0.4.0.SHBMIXM",
     "host": b"Android 12", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"21091116AI",  "software": b"MIUI.V125.0.7.0.SKLEUXM",
     "host": b"Android 12", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.24mm f/1.75",
     "focal_mm": (624, 100), "focal_35mm": 26, "f_number": (175, 100), "aperture_apex": (161, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"2106118C",    "software": b"MIUI.V130.0.5.0.SKGEUXM",
     "host": b"Android 12", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.7mm f/1.9",
     "focal_mm": (67, 10),  "focal_35mm": 26, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"22121119SG",  "software": b"MIUI.V140.0.6.0.SLBCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.24mm f/1.79",
     "focal_mm": (624, 100), "focal_35mm": 26, "f_number": (179, 100), "aperture_apex": (168, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"23123RN02Y",  "software": b"OS1.0.2.0.UMKCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.0mm f/1.65",
     "focal_mm": (60, 10),  "focal_35mm": 24, "f_number": (165, 100), "aperture_apex": (144, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"M2101K7BNY",  "software": b"MIUI.V120.0.7.0.RKZEUXM",
     "host": b"Android 11", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"22041219PG",  "software": b"MIUI.V140.0.4.0.SLBCNXM",
     "host": b"Android 12", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.24mm f/1.79",
     "focal_mm": (624, 100), "focal_35mm": 26, "f_number": (179, 100), "aperture_apex": (168, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"22120RN86G",  "software": b"MIUI.V140.0.3.0.SLBCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.3mm f/1.8",
     "focal_mm": (63, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Xiaomi", "model": b"23034RN054Y", "software": b"MIUI.V140.0.2.0.SLBCNXM",
     "host": b"Android 13", "lens_make": b"Xiaomi", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},

    # ── Apple iPhone (15) ─────────────────────────────────────────────────────
    {"make": b"Apple", "model": b"iPhone 15 Pro Max", "software": b"17.4.1",
     "host": b"iPhone16,2", "lens_make": b"Apple",
     "lens_model": b"iPhone 15 Pro Max back camera 6.765mm f/1.78",
     "focal_mm": (6765, 1000), "focal_35mm": 24, "f_number": (178, 100), "aperture_apex": (166, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 15 Pro",     "software": b"17.4.1",
     "host": b"iPhone16,1", "lens_make": b"Apple",
     "lens_model": b"iPhone 15 Pro back camera 6.765mm f/1.78",
     "focal_mm": (6765, 1000), "focal_35mm": 24, "f_number": (178, 100), "aperture_apex": (166, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 15 Plus",    "software": b"17.3.1",
     "host": b"iPhone15,5", "lens_make": b"Apple",
     "lens_model": b"iPhone 15 Plus back camera 5.7mm f/1.6",
     "focal_mm": (57, 10),  "focal_35mm": 26, "f_number": (16, 10), "aperture_apex": (136, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 15",         "software": b"17.3.0",
     "host": b"iPhone15,4", "lens_make": b"Apple",
     "lens_model": b"iPhone 15 back camera 5.7mm f/1.6",
     "focal_mm": (57, 10),  "focal_35mm": 26, "f_number": (16, 10), "aperture_apex": (136, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 14 Pro Max", "software": b"17.2.1",
     "host": b"iPhone15,3", "lens_make": b"Apple",
     "lens_model": b"iPhone 14 Pro Max back camera 7.7mm f/1.78",
     "focal_mm": (77, 10),  "focal_35mm": 24, "f_number": (178, 100), "aperture_apex": (166, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 14 Pro",     "software": b"17.2.0",
     "host": b"iPhone15,2", "lens_make": b"Apple",
     "lens_model": b"iPhone 14 Pro back camera 7.7mm f/1.78",
     "focal_mm": (77, 10),  "focal_35mm": 24, "f_number": (178, 100), "aperture_apex": (166, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 14 Plus",    "software": b"17.0.3",
     "host": b"iPhone14,8", "lens_make": b"Apple",
     "lens_model": b"iPhone 14 Plus back camera 5.1mm f/1.5",
     "focal_mm": (51, 10),  "focal_35mm": 26, "f_number": (15, 10), "aperture_apex": (117, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 14",         "software": b"16.7.2",
     "host": b"iPhone14,7", "lens_make": b"Apple",
     "lens_model": b"iPhone 14 back camera 5.1mm f/1.5",
     "focal_mm": (51, 10),  "focal_35mm": 26, "f_number": (15, 10), "aperture_apex": (117, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 13 Pro Max", "software": b"16.7.1",
     "host": b"iPhone14,3", "lens_make": b"Apple",
     "lens_model": b"iPhone 13 Pro Max back camera 5.7mm f/1.5",
     "focal_mm": (57, 10),  "focal_35mm": 26, "f_number": (15, 10), "aperture_apex": (117, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 13 Pro",     "software": b"16.7.0",
     "host": b"iPhone14,2", "lens_make": b"Apple",
     "lens_model": b"iPhone 13 Pro back camera 5.7mm f/1.5",
     "focal_mm": (57, 10),  "focal_35mm": 26, "f_number": (15, 10), "aperture_apex": (117, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 13",         "software": b"16.6.1",
     "host": b"iPhone14,5", "lens_make": b"Apple",
     "lens_model": b"iPhone 13 back camera 5.7mm f/1.6",
     "focal_mm": (57, 10),  "focal_35mm": 26, "f_number": (16, 10), "aperture_apex": (136, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 13 mini",    "software": b"16.5.1",
     "host": b"iPhone14,4", "lens_make": b"Apple",
     "lens_model": b"iPhone 13 mini back camera 5.7mm f/1.6",
     "focal_mm": (57, 10),  "focal_35mm": 26, "f_number": (16, 10), "aperture_apex": (136, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 12 Pro Max", "software": b"16.4.1",
     "host": b"iPhone13,4", "lens_make": b"Apple",
     "lens_model": b"iPhone 12 Pro Max back camera 5.1mm f/1.6",
     "focal_mm": (51, 10),  "focal_35mm": 26, "f_number": (16, 10), "aperture_apex": (136, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 12 Pro",     "software": b"16.3.1",
     "host": b"iPhone13,3", "lens_make": b"Apple",
     "lens_model": b"iPhone 12 Pro back camera 5.1mm f/2.0",
     "focal_mm": (51, 10),  "focal_35mm": 26, "f_number": (20, 10), "aperture_apex": (200, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Apple", "model": b"iPhone 12",         "software": b"16.2.1",
     "host": b"iPhone13,2", "lens_make": b"Apple",
     "lens_model": b"iPhone 12 back camera 5.1mm f/1.6",
     "focal_mm": (51, 10),  "focal_35mm": 26, "f_number": (16, 10), "aperture_apex": (136, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},

    # ── Huawei / Honor (8) ────────────────────────────────────────────────────
    {"make": b"Huawei", "model": b"VOG-L29", "software": b"10.1.0.176C00",
     "host": b"Android 10", "lens_make": b"LEICA", "lens_model": b"LEICA SUMMILUX-H 1:1.8/6.3",
     "focal_mm": (63, 10),  "focal_35mm": 27, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Huawei", "model": b"ELS-NX9", "software": b"11.0.0.170C00",
     "host": b"Android 10", "lens_make": b"LEICA", "lens_model": b"LEICA SUMMILUX-H 1:1.9/8.0",
     "focal_mm": (80, 10),  "focal_35mm": 23, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Huawei", "model": b"NOH-NX9", "software": b"11.0.0.162C00",
     "host": b"Android 10", "lens_make": b"LEICA", "lens_model": b"LEICA SUMMILUX-H 1:1.9/7.5",
     "focal_mm": (75, 10),  "focal_35mm": 23, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Huawei", "model": b"PGT-N19", "software": b"3.1.0.157C00",
     "host": b"HarmonyOS 3.1", "lens_make": b"LEICA",
     "lens_model": b"LEICA VARIO-SUMMILUX-H 1:1.4-4.0/7.7",
     "focal_mm": (77, 10),  "focal_35mm": 23, "f_number": (14, 10), "aperture_apex": (97, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"HONOR",  "model": b"ANY-NX1", "software": b"Magic UI 4.2.0",
     "host": b"Android 11", "lens_make": b"HONOR", "lens_model": b"Main Camera 6.0mm f/1.9",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"HONOR",  "model": b"CRT-NX1", "software": b"Magic UI 7.1.0",
     "host": b"Android 13", "lens_make": b"HONOR", "lens_model": b"Main Camera 7.09mm f/1.67",
     "focal_mm": (709, 100), "focal_35mm": 24, "f_number": (167, 100), "aperture_apex": (148, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"HONOR",  "model": b"VER-AN00", "software": b"MagicOS 7.2.0",
     "host": b"Android 13", "lens_make": b"HONOR", "lens_model": b"Main Camera 6.0mm f/1.95",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (195, 100), "aperture_apex": (193, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Huawei", "model": b"ALT-L29", "software": b"10.0.0.166C00",
     "host": b"Android 10", "lens_make": b"LEICA", "lens_model": b"LEICA SUMMILUX-H 1:1.8/7.5",
     "focal_mm": (75, 10),  "focal_35mm": 27, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},

    # ── OnePlus / OPPO / realme / vivo (14) ──────────────────────────────────
    {"make": b"OnePlus", "model": b"CPH2423", "software": b"CPH2423_11_A.09",
     "host": b"Android 13", "lens_make": b"OnePlus", "lens_model": b"Main Camera 6.2mm f/1.8",
     "focal_mm": (62, 10),  "focal_35mm": 23, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"OnePlus", "model": b"CPH2449", "software": b"CPH2449_11_A.07",
     "host": b"Android 13", "lens_make": b"Hasselblad",
     "lens_model": b"Hasselblad Camera 7.5mm f/1.8",
     "focal_mm": (75, 10),  "focal_35mm": 23, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"OnePlus", "model": b"CPH2399", "software": b"CPH2399_11_A.11",
     "host": b"Android 13", "lens_make": b"OnePlus", "lens_model": b"Main Camera 6.2mm f/1.8",
     "focal_mm": (62, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"OPPO", "model": b"CPH2269", "software": b"CPH2269_11_A.06",
     "host": b"Android 12", "lens_make": b"OPPO", "lens_model": b"Main Camera 6.1mm f/1.8",
     "focal_mm": (61, 10),  "focal_35mm": 24, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"OPPO", "model": b"CPH2413", "software": b"CPH2413_11_A.09",
     "host": b"Android 12", "lens_make": b"Hasselblad",
     "lens_model": b"Hasselblad Camera 7.5mm f/1.7",
     "focal_mm": (75, 10),  "focal_35mm": 23, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"OPPO", "model": b"CPH2239", "software": b"CPH2239_11_A.05",
     "host": b"Android 12", "lens_make": b"OPPO", "lens_model": b"Main Camera 6.4mm f/1.8",
     "focal_mm": (64, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"OPPO", "model": b"CPH2451", "software": b"CPH2451_13_A.04",
     "host": b"Android 13", "lens_make": b"OPPO", "lens_model": b"Main Camera 5.4mm f/2.0",
     "focal_mm": (54, 10),  "focal_35mm": 28, "f_number": (20, 10), "aperture_apex": (200, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"vivo", "model": b"V2254A", "software": b"PD2254F_EX_A_13.1.4.2",
     "host": b"Android 13", "lens_make": b"vivo", "lens_model": b"Main Camera 6.4mm f/1.7",
     "focal_mm": (64, 10),  "focal_35mm": 24, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"vivo", "model": b"V2207",  "software": b"PD2207F_EX_A_13.0.1.1",
     "host": b"Android 13", "lens_make": b"ZEISS",
     "lens_model": b"ZEISS T* Tessar 7.5mm f/1.57",
     "focal_mm": (75, 10),  "focal_35mm": 23, "f_number": (157, 100), "aperture_apex": (130, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"vivo", "model": b"V2218",  "software": b"PD2218F_EX_A_13.0.3.2",
     "host": b"Android 13", "lens_make": b"vivo", "lens_model": b"Main Camera 6.0mm f/2.0",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (20, 10), "aperture_apex": (200, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"realme", "model": b"RMX3741", "software": b"RMX3741_13.1.0.540",
     "host": b"Android 13", "lens_make": b"realme", "lens_model": b"Main Camera 6.3mm f/1.8",
     "focal_mm": (63, 10),  "focal_35mm": 25, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"realme", "model": b"RMX3686", "software": b"RMX3686_13.1.0.352",
     "host": b"Android 13", "lens_make": b"realme", "lens_model": b"Main Camera 6.2mm f/1.8",
     "focal_mm": (62, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"realme", "model": b"RMX3630", "software": b"RMX3630_13.0.0.120",
     "host": b"Android 13", "lens_make": b"realme", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"OPPO", "model": b"CPH2471", "software": b"CPH2471_13_A.06",
     "host": b"Android 13", "lens_make": b"OPPO", "lens_model": b"Main Camera 6.5mm f/1.9",
     "focal_mm": (65, 10),  "focal_35mm": 23, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},

    # ── Google Pixel (8) ──────────────────────────────────────────────────────
    {"make": b"Google", "model": b"Pixel 8 Pro", "software": b"AP2A.240805.005",
     "host": b"Android 14", "lens_make": b"Google",
     "lens_model": b"Pixel 8 Pro back camera 6.81mm f/1.68",
     "focal_mm": (681, 100), "focal_35mm": 24, "f_number": (168, 100), "aperture_apex": (144, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Google", "model": b"Pixel 8",     "software": b"AP2A.240805.005",
     "host": b"Android 14", "lens_make": b"Google",
     "lens_model": b"Pixel 8 back camera 6.25mm f/2.0",
     "focal_mm": (625, 100), "focal_35mm": 26, "f_number": (20, 10), "aperture_apex": (200, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Google", "model": b"Pixel 7 Pro", "software": b"PQ3A.230705.001",
     "host": b"Android 14", "lens_make": b"Google",
     "lens_model": b"Pixel 7 Pro back camera 7.7mm f/1.9",
     "focal_mm": (77, 10),  "focal_35mm": 23, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Google", "model": b"Pixel 7",     "software": b"PQ3A.230705.001",
     "host": b"Android 14", "lens_make": b"Google",
     "lens_model": b"Pixel 7 back camera 6.81mm f/1.85",
     "focal_mm": (681, 100), "focal_35mm": 25, "f_number": (185, 100), "aperture_apex": (178, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Google", "model": b"Pixel 7a",    "software": b"PQ3A.230705.001",
     "host": b"Android 14", "lens_make": b"Google",
     "lens_model": b"Pixel 7a back camera 6.81mm f/1.89",
     "focal_mm": (681, 100), "focal_35mm": 25, "f_number": (189, 100), "aperture_apex": (184, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Google", "model": b"Pixel 6 Pro", "software": b"TP1A.221005.002",
     "host": b"Android 13", "lens_make": b"Google",
     "lens_model": b"Pixel 6 Pro back camera 6.81mm f/1.85",
     "focal_mm": (681, 100), "focal_35mm": 24, "f_number": (185, 100), "aperture_apex": (178, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Google", "model": b"Pixel 6a",    "software": b"TP1A.221005.002",
     "host": b"Android 13", "lens_make": b"Google",
     "lens_model": b"Pixel 6a back camera 5.22mm f/1.7",
     "focal_mm": (522, 100), "focal_35mm": 27, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Google", "model": b"Pixel 6",     "software": b"TP1A.221005.002",
     "host": b"Android 13", "lens_make": b"Google",
     "lens_model": b"Pixel 6 back camera 6.81mm f/1.85",
     "focal_mm": (681, 100), "focal_35mm": 24, "f_number": (185, 100), "aperture_apex": (178, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},

    # ── Sony Xperia (5) ───────────────────────────────────────────────────────
    {"make": b"Sony", "model": b"XQ-BC72", "software": b"62.1.A.2.37",
     "host": b"Android 12", "lens_make": b"ZEISS",
     "lens_model": b"ZEISS Tessar T* 6.5mm f/1.7",
     "focal_mm": (65, 10),  "focal_35mm": 24, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Sony", "model": b"XQ-DQ72", "software": b"67.1.A.2.12",
     "host": b"Android 13", "lens_make": b"ZEISS",
     "lens_model": b"ZEISS Tessar T* 6.5mm f/1.7",
     "focal_mm": (65, 10),  "focal_35mm": 24, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Sony", "model": b"XQ-CT72", "software": b"64.2.A.3.2",
     "host": b"Android 12", "lens_make": b"ZEISS",
     "lens_model": b"ZEISS Tessar T* 6.5mm f/1.7",
     "focal_mm": (65, 10),  "focal_35mm": 24, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Sony", "model": b"XQ-EC72", "software": b"68.1.A.2.8",
     "host": b"Android 13", "lens_make": b"Sony",
     "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Sony", "model": b"PDX-217", "software": b"63.1.A.2.53",
     "host": b"Android 13", "lens_make": b"ZEISS",
     "lens_model": b"ZEISS Tessar T* 6.5mm f/1.7",
     "focal_mm": (65, 10),  "focal_35mm": 24, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},

    # ── Motorola (5) ─────────────────────────────────────────────────────────
    {"make": b"motorola", "model": b"XT2273-3", "software": b"T2TBS33.73-63-4-2",
     "host": b"Android 13", "lens_make": b"motorola", "lens_model": b"Main Camera 6.4mm f/1.7",
     "focal_mm": (64, 10),  "focal_35mm": 24, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"motorola", "model": b"XT2241-1", "software": b"S3RE33.20-42-11-11",
     "host": b"Android 13", "lens_make": b"motorola", "lens_model": b"Main Camera 6.0mm f/1.95",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (195, 100), "aperture_apex": (193, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"motorola", "model": b"XT2303-4", "software": b"T2TCS33.73-63-4",
     "host": b"Android 13", "lens_make": b"motorola", "lens_model": b"Main Camera 6.0mm f/1.9",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"motorola", "model": b"XT2333-3", "software": b"U4TBS33.73-86-3",
     "host": b"Android 13", "lens_make": b"motorola", "lens_model": b"Main Camera 6.4mm f/1.7",
     "focal_mm": (64, 10),  "focal_35mm": 24, "f_number": (17, 10), "aperture_apex": (153, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"motorola", "model": b"XT2341-3", "software": b"T3TS33.32-93-2",
     "host": b"Android 13", "lens_make": b"motorola", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},

    # ── Nokia (4) ────────────────────────────────────────────────────────────
    {"make": b"Nokia", "model": b"TA-1479", "software": b"00WW_3_480",
     "host": b"Android 12", "lens_make": b"Nokia", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Nokia", "model": b"TA-1561", "software": b"00WW_5_400",
     "host": b"Android 13", "lens_make": b"Nokia", "lens_model": b"Main Camera 6.4mm f/1.8",
     "focal_mm": (64, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Nokia", "model": b"TA-1526", "software": b"00WW_3_290",
     "host": b"Android 13", "lens_make": b"Nokia", "lens_model": b"Main Camera 6.0mm f/1.8",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"Nokia", "model": b"TA-1457", "software": b"00WW_3_410",
     "host": b"Android 12", "lens_make": b"Nokia", "lens_model": b"Main Camera 6.4mm f/1.8",
     "focal_mm": (64, 10),  "focal_35mm": 26, "f_number": (18, 10), "aperture_apex": (170, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},

    # ── LG (3) ───────────────────────────────────────────────────────────────
    {"make": b"LGE", "model": b"LM-V600", "software": b"V60T20g_00.DSGOKR",
     "host": b"Android 11", "lens_make": b"LG", "lens_model": b"Main Camera 7.78mm f/1.9",
     "focal_mm": (778, 100), "focal_35mm": 27, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"LGE", "model": b"LM-G900", "software": b"G900EMW20c_00.DSGOKR",
     "host": b"Android 11", "lens_make": b"LG", "lens_model": b"Main Camera 6.0mm f/1.9",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
    {"make": b"LGE", "model": b"LM-V500N", "software": b"V500N10h_00.KDSKR",
     "host": b"Android 10", "lens_make": b"LG", "lens_model": b"Main Camera 6.0mm f/1.9",
     "focal_mm": (60, 10),  "focal_35mm": 26, "f_number": (19, 10), "aperture_apex": (185, 100),
     "shutter_apex": (9966, 1000), "timezone": b"+03:00"},
]

FILE_PREFIXES = ["IMG", "DSC", "DSCF", "PXL", "CAM", "PHOTO", "MOB", "PIX"]

# Date range for random EXIF timestamps
_DATE_START     = date(2024, 1, 1)
_DATE_END       = date(2026, 5, 19)
_DATE_RANGE     = (_DATE_END - _DATE_START).days

WANTED_TAGS = {
    "Make", "Model", "Software", "DateTime", "DateTimeOriginal",
    "ISOSpeedRatings", "FNumber", "ExposureTime", "FocalLength",
    "Flash", "Artist", "Copyright",
}
GPS_IFD_TAG = 0x8825


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def random_filename(ext: str = "jpg") -> str:
    """
    16-character base name: PREFIX_ + random alphanumeric tail.
    Example: IMG_a3f8b2c9e1d7.jpg  (4 prefix + _ + 11 tail = 16 chars)
    """
    prefix = random.choice(FILE_PREFIXES)
    tail_len = 16 - len(prefix) - 1          # subtract prefix + underscore
    tail = "".join(random.choices(string.ascii_lowercase + string.digits, k=tail_len))
    return f"{prefix}_{tail}.{ext}"


def random_exif_dt(rng: random.Random) -> bytes:
    """Random datetime between 2024-01-01 and today, realistic daytime hours."""
    d = _DATE_START + timedelta(days=rng.randint(0, _DATE_RANGE))
    h = rng.randint(7, 21)
    m = rng.randint(0, 59)
    s = rng.randint(0, 59)
    return f"{d.year}:{d.month:02d}:{d.day:02d} {h:02d}:{m:02d}:{s:02d}".encode()


def count_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f"count:{i}") for i in range(1, 6)],
        [InlineKeyboardButton(str(i), callback_data=f"count:{i}") for i in range(6, 11)],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# EXIF
# ─────────────────────────────────────────────────────────────────────────────

def extract_original_metadata(img_bytes: bytes) -> dict:
    info = {}
    try:
        image = Image.open(io.BytesIO(img_bytes))
        exif = image.getexif()
        if not exif:
            return info
        for tag_id, value in exif.items():
            name = TAGS.get(tag_id)
            if name not in WANTED_TAGS:
                continue
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace").strip("\x00")
            if name == "FNumber":
                try:
                    value = f"f/{float(value):.1f}"
                except Exception:
                    value = str(value)
            elif name == "ExposureTime":
                try:
                    value = f"1/{int(1 / float(value))}"
                except Exception:
                    value = str(value)
            else:
                value = str(value).strip()
            if value:
                info[name] = value
        if exif.get_ifd(GPS_IFD_TAG):
            info["GPS"] = "присутствуют координаты"
    except Exception as e:
        logger.warning(f"EXIF read failed: {e}")
    return info


def make_fake_exif(
    copy_index: int,
    camera_index: int,
    width: int = 4080,
    height: int = 3060,
) -> bytes:
    """
    Build a maximally populated EXIF block (66 fields across IFD0 + ExifIFD).
    Per-copy uniqueness: timestamp subseconds, ISO, brightness, serial numbers,
    ImageUniqueID. Per-camera uniqueness: optics, firmware, timezone, OS.
    """
    cam = CAMERAS[camera_index % len(CAMERAS)]
    rng = random.Random(copy_index * 1337 + camera_index * 7919)

    # ── timestamp: random date 2024-01-01 → today, realistic hour ────────────
    dt     = random_exif_dt(rng)
    subsec = str(rng.randint(100, 999)).encode()

    # ── unique identifiers per copy ──────────────────────────────────────────
    body_serial  = f"R{rng.randint(10_000_000, 99_999_999)}".encode()
    lens_serial  = f"L{rng.randint(10_000_000, 99_999_999)}".encode()
    image_uid    = f"{rng.randint(0, 2**128 - 1):032x}".encode()  # 32 hex chars

    # ── exposure variation ───────────────────────────────────────────────────
    iso           = rng.choice([50, 64, 80, 100, 125])
    brightness    = (rng.randint(210, 290), 100)
    f_num         = cam["f_number"]
    focal         = cam["focal_mm"]
    lens_spec     = (focal, focal, f_num, f_num)   # prime lens: min=max

    # ── subject area: centered rectangle ────────────────────────────────────
    cx, cy = width // 2, height // 2
    sw, sh = width // 2, height // 2

    exif_dict = {
        # ── IFD0: 12 fields ────────────────────────────────────────────────
        "0th": {
            piexif.ImageIFD.Make:             cam["make"],
            piexif.ImageIFD.Model:            cam["model"],
            piexif.ImageIFD.Orientation:      1,              # Normal (no rotation)
            piexif.ImageIFD.XResolution:      (72, 1),
            piexif.ImageIFD.YResolution:      (72, 1),
            piexif.ImageIFD.ResolutionUnit:   2,              # Inch
            piexif.ImageIFD.Software:         cam["software"],
            piexif.ImageIFD.DateTime:         dt,
            piexif.ImageIFD.HostComputer:     cam["host"],
            piexif.ImageIFD.Artist:           b"",
            piexif.ImageIFD.Copyright:        b"",
            piexif.ImageIFD.YCbCrPositioning: 1,              # Centered
        },
        # ── ExifIFD: 54 fields ─────────────────────────────────────────────
        "Exif": {
            # Exposure
            piexif.ExifIFD.ExposureTime:              (1, 1000),
            piexif.ExifIFD.FNumber:                   f_num,
            piexif.ExifIFD.ExposureProgram:           2,      # Normal program
            piexif.ExifIFD.ISOSpeedRatings:           iso,
            piexif.ExifIFD.SensitivityType:           3,      # ISO Speed
            piexif.ExifIFD.StandardOutputSensitivity: iso,
            piexif.ExifIFD.RecommendedExposureIndex:  iso,
            piexif.ExifIFD.ExposureBiasValue:         (0, 10),
            piexif.ExifIFD.ExposureMode:              0,      # Auto
            piexif.ExifIFD.ExposureIndex:             (iso, 1),

            # Version & datetime
            piexif.ExifIFD.ExifVersion:               b"0232",
            piexif.ExifIFD.DateTimeOriginal:          dt,
            piexif.ExifIFD.DateTimeDigitized:         dt,
            piexif.ExifIFD.OffsetTime:                cam["timezone"],
            piexif.ExifIFD.OffsetTimeOriginal:        cam["timezone"],
            piexif.ExifIFD.OffsetTimeDigitized:       cam["timezone"],
            piexif.ExifIFD.SubSecTime:                subsec,
            piexif.ExifIFD.SubSecTimeOriginal:        subsec,
            piexif.ExifIFD.SubSecTimeDigitized:       subsec,

            # Optics & APEX values
            piexif.ExifIFD.ApertureValue:             cam["aperture_apex"],
            piexif.ExifIFD.MaxApertureValue:          cam["aperture_apex"],
            piexif.ExifIFD.ShutterSpeedValue:         cam["shutter_apex"],
            piexif.ExifIFD.BrightnessValue:           brightness,
            piexif.ExifIFD.FocalLength:               focal,
            piexif.ExifIFD.FocalLengthIn35mmFilm:     cam["focal_35mm"],
            piexif.ExifIFD.DigitalZoomRatio:          (1, 1),   # No zoom
            piexif.ExifIFD.FocalPlaneXResolution:     (width * 1000, 1),
            piexif.ExifIFD.FocalPlaneYResolution:     (height * 1000, 1),
            piexif.ExifIFD.FocalPlaneResolutionUnit:  3,         # Centimeter

            # Light & metering
            piexif.ExifIFD.MeteringMode:              2,      # Center-weighted
            piexif.ExifIFD.LightSource:               0,      # Auto
            piexif.ExifIFD.WhiteBalance:              0,      # Auto
            piexif.ExifIFD.Flash:                     16,     # No flash, suppressed

            # Image structure
            piexif.ExifIFD.ComponentsConfiguration:   b"\x01\x02\x03\x00",  # YCbCr
            piexif.ExifIFD.FlashpixVersion:           b"0100",
            piexif.ExifIFD.ColorSpace:                1,      # sRGB
            piexif.ExifIFD.PixelXDimension:           width,
            piexif.ExifIFD.PixelYDimension:           height,
            piexif.ExifIFD.Gamma:                     (220, 100),  # γ=2.2 (sRGB)

            # Scene & rendering
            piexif.ExifIFD.SensingMethod:             2,      # One-chip color area sensor
            piexif.ExifIFD.FileSource:                b"\x03",  # Digital camera
            piexif.ExifIFD.SceneType:                 b"\x01",  # Directly photographed
            piexif.ExifIFD.CustomRendered:            0,      # Normal process
            piexif.ExifIFD.SceneCaptureType:          0,      # Standard
            piexif.ExifIFD.GainControl:               0,      # None
            piexif.ExifIFD.Contrast:                  0,      # Normal
            piexif.ExifIFD.Saturation:                0,      # Normal
            piexif.ExifIFD.Sharpness:                 0,      # Normal
            piexif.ExifIFD.SubjectDistanceRange:      2,      # Close view

            # Subject
            piexif.ExifIFD.SubjectArea:               (cx, cy, sw, sh),
            piexif.ExifIFD.UserComment:               b"ASCII\x00\x00\x00",

            # Identifiers (unique per copy)
            piexif.ExifIFD.ImageUniqueID:             image_uid,
            piexif.ExifIFD.CameraOwnerName:           b"",
            piexif.ExifIFD.BodySerialNumber:          body_serial,
            piexif.ExifIFD.LensSpecification:         lens_spec,
            piexif.ExifIFD.LensMake:                  cam["lens_make"],
            piexif.ExifIFD.LensModel:                 cam["lens_model"],
            piexif.ExifIFD.LensSerialNumber:          lens_serial,
        },
        "GPS": {},
        "1st": {},
        "thumbnail": None,
    }
    return piexif.dump(exif_dict)


# ─────────────────────────────────────────────────────────────────────────────
# Image processing
# ─────────────────────────────────────────────────────────────────────────────

def apply_color_correction(image: Image.Image, rng: random.Random) -> Image.Image:
    """
    Subtle color adjustments — each value is below human JND,
    but together they shift the perceptual hash reliably.
    """
    image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.97, 1.03))
    image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.97, 1.03))
    image = ImageEnhance.Color(image).enhance(rng.uniform(0.95, 1.05))
    image = ImageEnhance.Sharpness(image).enhance(rng.uniform(0.97, 1.03))

    # Per-channel micro-offset ±2
    arr = np.array(image, dtype=np.int16)
    for c in range(3):
        arr[:, :, c] = np.clip(arr[:, :, c] + rng.randint(-2, 2), 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def apply_invisible_noise(image: Image.Image, rng: random.Random) -> Image.Image:
    """±2 noise per pixel — below human JND, unique binary fingerprint."""
    np_rng = np.random.default_rng(rng.randint(0, 2**31))
    arr = np.array(image, dtype=np.int16)
    noise = np_rng.integers(-2, 3, arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def make_copy(img_bytes: bytes, copy_index: int, camera_index: int) -> tuple[io.BytesIO, str]:
    rng = random.Random(random.randint(0, 2**31) + copy_index * 997)

    image = Image.open(io.BytesIO(img_bytes))
    if image.mode != "RGB":
        image = image.convert("RGB")

    image = apply_color_correction(image, rng)
    image = apply_invisible_noise(image, rng)

    width, height = image.size
    exif_bytes = make_fake_exif(copy_index, camera_index, width, height)
    quality = 94 + (copy_index % 3)  # 94/95/96 — extra entropy in compression

    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif_bytes, quality=quality)
    buf.seek(0)

    return buf, random_filename("jpg")


# ─────────────────────────────────────────────────────────────────────────────
# Job: trigger count prompt after 2 s of photo inactivity
# ─────────────────────────────────────────────────────────────────────────────

async def job_ask_count(context: ContextTypes.DEFAULT_TYPE) -> None:
    n = len(context.user_data.get("batch", []))
    if n == 0:
        return
    context.user_data["state"] = STATE_WAITING
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"📷 Получено {n} фото. Сколько уникальных копий сделать для *каждого*?",
        reply_markup=count_keyboard(),
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data["state"] = STATE_IDLE
    await update.message.reply_text(
        "Отправь от 1 до 10 фото (можно альбомом или по одному).\n\n"
        "Бот сделает N уникальных копий каждого:\n"
        "• Цветокоррекция + невидимый шум\n"
        "• Поддельный EXIF (рандомная камера, уникальная дата)\n"
        "• GPS удалён\n"
        "• Рандомные имена файлов"
    )


async def _add_to_batch(
    update: Update, context: ContextTypes.DEFAULT_TYPE, img_bytes: bytes
) -> None:
    state = context.user_data.get("state", STATE_IDLE)

    if state == STATE_PROCESSING:
        await update.message.reply_text("⏳ Идёт обработка, подожди...")
        return

    if state == STATE_WAITING:
        # New photo after prompt — start fresh batch
        context.user_data["batch"] = []
        context.user_data["state"] = STATE_IDLE

    batch: list = context.user_data.setdefault("batch", [])

    if len(batch) >= 10:
        await update.message.reply_text("Максимум 10 фото. Выбери количество копий кнопкой выше.")
        return

    batch.append(img_bytes)
    context.user_data["state"] = STATE_COLLECTING
    n = len(batch)

    # Reset the 2-second timer
    for job in context.job_queue.get_jobs_by_name(f"ask_{update.effective_user.id}"):
        job.schedule_removal()

    context.job_queue.run_once(
        job_ask_count,
        when=2.0,
        name=f"ask_{update.effective_user.id}",
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
    )

    hint = "ещё можно добавить" if n < 10 else "максимум, жди кнопку"
    await update.message.reply_text(f"📷 {n}/10 — {hint}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    img_bytes = bytes(await file.download_as_bytearray())
    await _add_to_batch(update, context, img_bytes)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        return
    file = await context.bot.get_file(doc.file_id)
    img_bytes = bytes(await file.download_as_bytearray())
    await _add_to_batch(update, context, img_bytes)


async def handle_count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    n_copies = int(query.data.split(":")[1])
    batch: list = context.user_data.get("batch", [])

    if not batch:
        await query.edit_message_text("Сначала отправь фото.")
        return

    context.user_data["state"] = STATE_PROCESSING
    n_photos = len(batch)
    total_files = n_photos * n_copies

    await query.edit_message_text(
        f"⏳ Генерирую {total_files} файлов ({n_photos} фото × {n_copies} копий)..."
    )

    errors = 0
    zip_files: list[tuple[str, bytes]] = []

    try:
        for photo_idx, img_bytes in enumerate(batch):
            for copy_idx in range(1, n_copies + 1):
                unique_index = photo_idx * 100 + copy_idx
                camera_index = photo_idx + copy_idx
                try:
                    buf, filename = make_copy(img_bytes, unique_index, camera_index)
                    raw = buf.read()
                    zip_files.append((filename, raw))
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=io.BytesIO(raw),
                        filename=filename,
                    )
                except Exception:
                    logger.exception(f"Error photo {photo_idx + 1} copy {copy_idx}")
                    errors += 1

        context.user_data["zip_files"] = zip_files

        summary = f"✅ {total_files - errors} файлов готово"
        if errors:
            summary += f" ({errors} ошибок)"
        summary += "\n\nМожно сразу отправить следующие фото."

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=summary,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📦 Скачать ZIP", callback_data="dl_zip"),
            ]]),
        )
    except Exception:
        logger.exception("Fatal error during processing")
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Ошибка при обработке. Отправь фото заново.",
            )
        except Exception:
            pass
    finally:
        # Сбрасываем состояние и батч в любом случае — бот всегда готов к новой работе
        context.user_data["state"] = STATE_IDLE
        context.user_data["batch"] = []


async def handle_zip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Собираю архив…")

    zip_files: list = context.user_data.get("zip_files", [])
    if not zip_files:
        await query.edit_message_text("Файлы уже недоступны. Обработай заново.")
        return

    await query.edit_message_reply_markup(reply_markup=None)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, raw in zip_files:
            zf.writestr(filename, raw)
    zip_buf.seek(0)

    await context.bot.send_document(
        chat_id=query.message.chat_id,
        document=zip_buf,
        filename=f"batch_{len(zip_files)}_files.zip",
        caption=f"📦 {len(zip_files)} файлов в архиве",
    )

    context.user_data.pop("zip_files", None)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("Укажи BOT_TOKEN в .env")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    app.add_handler(CallbackQueryHandler(handle_count_callback, pattern=r"^count:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_zip_callback,   pattern=r"^dl_zip$"))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
