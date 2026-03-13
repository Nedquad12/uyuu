import sys
import time
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
import logging
import pandas as pd
import os
import glob
from datetime import datetime
import matplotlib.pyplot as plt
import io
import gc
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import matplotlib.dates as mdates
import mplfinance as mpf
import numpy as np