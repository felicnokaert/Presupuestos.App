import pandas as pd
import sqlite3
import os
import sys
import traceback

# --- Configuración de Archivos ---
CSV_PRECIOS_PATH = 'Lista de Precios - Costos.csv' # Nombre de tu archivo CSV de precios
DB_NAME = 'presupuestos.db' # Nombre del archivo de la base de datos SQLite
TABLE_NAME = 'productos' # Nombre de la tabla donde se guardarán los productos
DB_HISTORY_TABLE_NAME = 'presupuestos_guardados' # Nombre de la tabla para el historial

# Tasa de IVA (la usaremos para quitar el IVA al importar si los precios del CSV lo tenían)
IVA_RATE = 0.21

print(f"DEBUG: [INICIO] Iniciando script de importación...")
print(f"DEBUG: Archivo CSV de precios: {CSV_PRECIOS_PATH}")
print(f"DEBUG: Archivo DB SQLite: {DB_NAME}")

try:
    # 1. Eliminar base de datos antigua (si existe) para empezar de cero
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"DEBUG: Archivo '{DB_NAME}' existente eliminado para crear uno nuevo.")

    # 2. Leer el CSV con la configuración exacta para tu formato actual
    # header=0: La primera fila es el encabezado.
    # sep=';': El delimitador es el PUNTO Y COMA (;) - CRUCIAL para tu CSV.
    # decimal=',': El separador decimal es la COMA (,) - CRUCIAL para números como "19,50".
    df = pd.read_csv(CSV_PRECIOS_PATH, sep=';', encoding='latin-1', header=0, decimal=',')

    print(f"DEBUG: CSV leído exitosamente en DataFrame. Primeras 5 filas:\n{df.head()}")
    print(f"DEBUG: Columnas del DataFrame inicial: {list(df.columns)}")
    print(f"DEBUG: Tipos de datos iniciales:\n{df.dtypes}")

    # 3. Normalizar nombres de columnas para que coincidan con los que usaremos en la DB
    # Convertir a mayúsculas y limpiar espacios.
    df.columns = df.columns.astype(str).str.strip().str.upper()

    # Mapeo de nombres de columnas del CSV (después de .upper()) a nombres de columnas de la DB
    COL_MAPPING = {
        'PRODUCTOS': 'nombre_producto',
        'COSTO': 'costo_base',
        '0,1': 'precio_0_1',       # Encabezado '0,1' con coma (si está en el CSV)
        '1': 'precio_1',
        '5': 'precio_5',
        '10': 'precio_10',       # El encabezado '10' (sin '-dic')
        '25': 'precio_25',
        'TAMBOR - ROLLO': 'precio_tambor_rollo'
    }

    # Verificar si las columnas esperadas existen ANTES de renombrar
    missing_csv_cols = [col for col in COL_MAPPING.keys() if col not in df.columns]
    if missing_csv_cols:
        print(f"ERROR: Columnas esperadas en el CSV: {list(COL_MAPPING.keys())}", file=sys.stderr)
        print(f"ERROR: Columnas encontradas en el DataFrame: {list(df.columns)}", file=sys.stderr)
        raise ValueError(f"Faltan columnas esenciales en el CSV: {', '.join(missing_csv_cols)}. Revise los nombres de encabezado en su CSV (mayúsculas, sin espacios extra) y el delimitador.")

    # Renombrar las columnas en el DataFrame
    df = df.rename(columns=COL_MAPPING)

    # Seleccionar solo las columnas relevantes por sus nombres internos
    df = df[[
        'nombre_producto', 'costo_base', 'precio_0_1', 'precio_1', 'precio_5',
        'precio_10', 'precio_25', 'precio_tambor_rollo'
    ]].copy()

    print(f"DEBUG: DataFrame después de renombrar y seleccionar columnas:\n{df.head()}")

    # 4. Limpiar y convertir datos a numérico, quitando IVA
    price_cols = [
        'costo_base', 'precio_0_1', 'precio_1', 'precio_5',
        'precio_10', 'precio_25', 'precio_tambor_rollo'
    ]

    for col in price_cols:
        print(f"DEBUG: Procesando columna de precio: {col}. Tipo inicial: {df[col].dtype}")
        
        clean_strings = df[col].astype(str).str.strip() 
        
        numeric_vals = pd.to_numeric(clean_strings, errors='coerce')
        
        df.loc[:, col] = numeric_vals.apply(lambda x: round(x / (1 + IVA_RATE), 4) if pd.notna(x) and x > 0 else 0.0)
        print(f"DEBUG: Columna {col} después de procesamiento (primeros 5):\n{df[col].head()}")
    
    print(f"DEBUG: DataFrame después de limpieza y procesamiento de precios:\n{df.head()}")
    print(f"DEBUG: Tipo de datos finales de las columnas de precio: \n{df[price_cols].dtypes}")

    # 5. Asegurarse de que el nombre del producto no sea nulo o vacío
    initial_rows = len(df)
    df = df.dropna(subset=['nombre_producto'])
    df = df[df['nombre_producto'] != ''].copy()
    print(f"DEBUG: Filas después de filtrar nombres (NaN/vacío): {initial_rows} -> {len(df)}")
    
    if df.empty:
        raise ValueError("DataFrame vacío después de la limpieza. No hay productos válidos para importar.")

    # 6. Conectar a la base de datos SQLite y guardar el DataFrame
    print(f"DEBUG: Conectando a la base de datos '{DB_NAME}' y guardando en la tabla '{TABLE_NAME}'")
    conn = sqlite3.connect(DB_NAME)
    
    df.to_sql(TABLE_NAME, conn, if_exists='replace', index=False)
    
    print(f"DEBUG: Creando tabla '{DB_HISTORY_TABLE_NAME}' para el historial de presupuestos.")
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_HISTORY_TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_presupuesto INTEGER NOT NULL UNIQUE,
            fecha_presupuesto TEXT NOT NULL,
            razon_social_cliente TEXT NOT NULL,
            documento_cliente TEXT,
            total_usd REAL NOT NULL,
            total_ars REAL NOT NULL,
            tipo_cambio REAL NOT NULL,
            metodo_pago TEXT,
            detalles_pago TEXT,
            fecha_guardado TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    conn.close()
    print(f"DEBUG: [FIN] ¡Importación completada! Los datos de productos se guardaron en la tabla '{TABLE_NAME}' en '{DB_NAME}'.")

except FileNotFoundError:
    print(f"ERROR: El archivo CSV '{CSV_PRECIOS_PATH}' no fue encontrado. Asegúrese de que esté en la misma carpeta y su nombre sea correcto.", file=sys.stderr)
except pd.errors.EmptyDataError:
    print(f"ERROR: El archivo CSV '{CSV_PRECIOS_PATH}' está vacío o no contiene datos válidos después de la lectura inicial.", file=sys.stderr)
except Exception as e:
    print(f"ERROR: Ocurrió un error inesperado durante la importación del CSV a SQLite: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)