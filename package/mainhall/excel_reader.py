import pandas as pd
import logging
from imporh import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_file_date_from_name(filename):
    """Extract date from filename format ddmmyy.xlsx"""
    try:
        date_str = filename.replace('.xlsx', '').replace('.xls', '')
        if len(date_str) == 6:
            day = int(date_str[:2])
            month = int(date_str[2:4])
            year = 2000 + int(date_str[4:6])
            return datetime(year, month, day)
    except ValueError as e:
        logger.warning(f"Cannot parse date from filename {filename}: {e}")
    return None

def get_excel_files(directory):
    """Get all excel files sorted by date"""
    files = []
    for filename in os.listdir(directory):
        if filename.endswith(('.xlsx', '.xls')):
            file_date = get_file_date_from_name(filename)
            if file_date:
                files.append({
                    'filename': filename,
                    'date': file_date,
                    'path': os.path.join(directory, filename)
                })
    
    files.sort(key=lambda x: x['date'], reverse=True)
    return files

def get_stock_sector_data(stock_code):
    """Get sector information for specific stock"""
    try:
        sector_directory = "/home/ec2-user/database/namesektor"
        
        if not os.path.exists(sector_directory):
            return None, "Direktori sektor tidak ditemukan"
        
        # Get all sector files
        sector_files = [f for f in os.listdir(sector_directory) if f.endswith(('.xlsx', '.xls'))]
        
        if not sector_files:
            return None, "Tidak ada file sektor ditemukan"
        
        # Search through each sector file
        for sector_file in sector_files:
            sector_name = sector_file.replace('.xlsx', '').replace('.xls', '')
            file_path = os.path.join(sector_directory, sector_file)
            
            try:
                # Read sector file
                df = pd.read_excel(file_path, header=None)
                
                if df.shape[1] >= 6:  # Make sure we have at least 6 columns (A-F)
                    # Extract data from specified columns
                    sector_data = {
                        'kode': df.iloc[:, 1],           # Column B - Kode
                        'tanggal_pencatatan': df.iloc[:, 3],  # Column D - Tanggal Pencatatan
                        'papan_pencatatan': df.iloc[:, 5]     # Column F - Papan Pencatatan
                    }
                    
                    sector_df = pd.DataFrame(sector_data)
                    sector_df = sector_df.dropna(subset=['kode'])
                    
                    # Clean kode and convert to string
                    sector_df['kode'] = sector_df['kode'].astype(str).str.strip().str.upper()
                    
                    # Search for the stock code
                    stock_row = sector_df[sector_df['kode'] == stock_code.upper()]
                    
                    if not stock_row.empty:
                        stock_info = stock_row.iloc[0]
                        
                        analysis = {
                            'stock_code': stock_code,
                            'sector': sector_name,
                            'tanggal_pencatatan': stock_info['tanggal_pencatatan'],
                            'papan_pencatatan': stock_info['papan_pencatatan']
                        }
                        
                        return analysis, None
                        
            except Exception as e:
                logger.warning(f"Error reading sector file {sector_file}: {e}")
                continue
        
        # If not found in any sector
        return None, f"Saham {stock_code} tidak ditemukan di data sektor"
        
    except Exception as e:
        logger.error(f"Error in get_stock_sector_data: {e}")
        return None, "Error saat menganalisis data sektor"

def read_excel_data(file_path):
    """Read excel data and extract all required columns"""
    try:
        df = pd.read_excel(file_path, header=None)
        
        # Log the actual number of columns found
        logger.info(f"File {file_path} has {df.shape[1]} columns")
        
        # Define all possible columns with their indices
        column_mapping = [
            (0, 'No'),                      # Column A
            (1, 'kode_saham'),             # Column B
            (2, 'nama_perusahaan'),        # Column C
            (3, 'remarks'),                # Column D
            (4, 'sebelumnya'),             # Column E
            (5, 'open_price'),             # Column F
            (6, 'tanggal_perdagangan_terakhir'),           # Column G       
            (7, 'first_trade'),            # Column J
            (8, 'tertinggi'),             # Column K
            (9, 'terendah'),              # Column L
            (10, 'penutupan'),             # Column M
            (11, 'selisih'),               # Column N
            (12, 'volume'),                # Column O
            (13, 'nilai'),                 # Column P
            (14, 'frekuensi'),             # Column Q
            (15, 'index_individual'),      # Column R
            (16, 'offer'),                 # Column S
            (17, 'offer_volume'),          # Column T
            (18, 'bid'),                   # Column U
            (19, 'bid_volume'),            # Column V
            (20, 'listed_shares'),         # Column W
            (21, 'tradeable_shares'),      # Column X 
            (22, 'weight_for_index'),      # Column Y 
            (23, 'foreign_sell'),          # Column Z
            (24, 'foreign_buy'),           # Column AA
            (25, 'non_regular_volume'),    # Column AB
            (26, 'non_regular_Value'),     # Column AC
            (27, 'non_regular_Frequency')  # Column AD
        ]
        
        # Check minimum required columns (at least kode_saham)
        if df.shape[1] >= 2:
            data = {}
            
            # Add columns that exist in the file
            for col_index, col_name in column_mapping:
                if col_index < df.shape[1]:
                    data[col_name] = df.iloc[:, col_index]
                else:
                    # Add empty column with None values for missing columns
                    data[col_name] = None
                    logger.warning(f"Column {col_name} (index {col_index}) not found in file, filling with None")
            
            result_df = pd.DataFrame(data)
            result_df = result_df.dropna(subset=['kode_saham'])
            
            # Clean kode_saham and convert to string
            result_df['kode_saham'] = result_df['kode_saham'].astype(str).str.strip().str.upper()
            
            # Define numeric columns for conversion
            numeric_cols = [
                'sebelumnya', 'open_price', 'Terakhir', 'first_trade', 'tertinggi', 
                'terendah', 'penutupan', 'selisih', 'volume', 'nilai', 'frekuensi',
                'index_individual', 'offer', 'offer_volume', 'bid', 'bid_volume',
                'listed_shares', 'tredeable_shares', 'weight_for_index',
                'foreign_sell', 'foreign buy', 'non_regular_volume', 
                'non_regular_Value', 'non_regular_Frequency'
            ]
            
            # Convert numeric columns
            for col in numeric_cols:
                if col in result_df.columns:
                    result_df[col] = pd.to_numeric(result_df[col], errors='coerce').fillna(0)
            
            # Calculate foreign net flow (only if both columns exist)
            if 'foreign buy' in result_df.columns and 'foreign_sell' in result_df.columns:
                if result_df['foreign buy'].notna().any() and result_df['foreign_sell'].notna().any():
                    result_df['Foreign_Net'] = result_df['foreign buy'] - result_df['foreign_sell']
                else:
                    result_df['foreign_net'] = 0
            else:
                result_df['foreign_net'] = 0
            
            logger.info(f"Successfully read {len(result_df)} rows from {file_path}")
            return result_df
        else:
            logger.error(f"File {file_path} doesn't have enough columns (found {df.shape[1]}, need at least 2 for kode_saham)")
            return None
            
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return None