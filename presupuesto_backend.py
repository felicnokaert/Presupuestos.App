import sqlite3
import pandas as pd
import gspread
from PIL import Image
import pytesseract
import re
import os
import datetime

# --- CONFIGURACIÓN OPCIONAL PARA TESSERACT (solo si no está en tu PATH) ---
# Si Tesseract OCR no está en tu PATH, descomenta la línea de abajo
# y reemplaza la ruta con la ubicación real del ejecutable tesseract.exe
# Ejemplo para Windows:
pytesseract.pytesseract.tesseract_cmd = r'D:\Poliplast\Felipe\Tesseract\tesseract.exe' # <--- ASEGÚRATE QUE ESTA RUTA SEA CORRECTA
# Ejemplo para macOS (si instalaste con Homebrew):
# pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'


# --- 1. Funciones de Base de Datos (SQLite) ---

def inicializar_base_de_datos():
    """Crea las tablas de clientes, comprobantes, productos, notas_pedido y presupuestos si no existen."""
    conn = sqlite3.connect('presupuestos.db') # Conexión a la DB unificada
    cursor = conn.cursor()

    # Tabla de Clientes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        cuit TEXT NOT NULL,
        razon_social TEXT NOT NULL
    )
    """)

    # Tabla de Comprobantes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comprobantes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nro_operacion TEXT UNIQUE NOT NULL,
        fecha TEXT,
        importe REAL,
        cuenta TEXT,
        cliente_id INTEGER,
        FOREIGN KEY(cliente_id) REFERENCES clientes(id)
    )
    """)

    # --- TABLA DE PRODUCTOS (ACTUALIZADA con las columnas de precios del CSV) ---
    # Esta tabla debe ser compatible con lo que importa import_data_to_sql.py
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE NOT NULL,                   -- SKU o código del producto
        descripcion TEXT NOT NULL,                    -- Nombre del producto
        stock_disponible INTEGER NOT NULL DEFAULT 0,  -- Cantidad en stock físico
        stock_reservado INTEGER NOT NULL DEFAULT 0,   -- Cantidad reservada por pedidos
        estado_producto TEXT NOT NULL DEFAULT 'disponible', -- Estado general del producto
        -- Columnas de precios importadas del CSV
        costo_base REAL NOT NULL DEFAULT 0.0,
        precio_0_1 REAL NOT NULL DEFAULT 0.0,
        precio_1 REAL NOT NULL DEFAULT 0.0,
        precio_5 REAL NOT NULL DEFAULT 0.0,
        precio_10 REAL NOT NULL DEFAULT 0.0,
        precio_25 REAL NOT NULL DEFAULT 0.0,
        precio_tambor_rollo REAL NOT NULL DEFAULT 0.0
    )
    """)

    # Tabla de Notas de Pedido
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notas_pedido (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        fecha_creacion TEXT NOT NULL,
        tipo_entrega TEXT NOT NULL DEFAULT 'Retiro por mostrador',
        direccion_envio TEXT,
        telefono_contacto TEXT,
        estado TEXT NOT NULL DEFAULT 'pendiente',
        FOREIGN KEY (cliente_id) REFERENCES clientes(id)
    )
    """)

    # Tabla de Detalle de Pedido
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS detalle_pedido (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nota_pedido_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        cantidad INTEGER NOT NULL,
        precio_unitario REAL NOT NULL,
        FOREIGN KEY (nota_pedido_id) REFERENCES notas_pedido(id),
        FOREIGN KEY (producto_id) REFERENCES productos(id)
    )
    """)

    # Tabla de Presupuestos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS presupuestos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        fecha_creacion TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'borrador',
        FOREIGN KEY (cliente_id) REFERENCES clientes(id)
    )
    """)

    # Tabla de Detalle de Presupuesto
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS detalle_presupuesto (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        presupuesto_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        cantidad INTEGER NOT NULL,
        precio_unitario REAL NOT NULL,
        FOREIGN KEY (presupuesto_id) REFERENCES presupuestos(id),
        FOREIGN KEY (producto_id) REFERENCES productos(id)
    )
    """)

    conn.commit()
    conn.close()
    print("Base de datos y tablas verificadas/creadas (incluyendo todos los módulos).")


def obtener_o_crear_cliente(nombre):
    """Busca un cliente por nombre; si no existe, pide CUIT y Razón Social para crearlo."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM clientes WHERE nombre = ?", (nombre,))
    cliente = cursor.fetchone()

    if cliente:
        print(f"✅ Cliente '{nombre}' encontrado.")
        cliente_id = cliente[0]
    else:
        print(f"❌ Cliente '{nombre}' no existe. Vamos a registrarlo.")
        cuit = input("Ingrese CUIT: ")
        razon_social = input("Ingrese razón social: ")
        try:
            cursor.execute("INSERT INTO clientes (nombre, cuit, razon_social) VALUES (?, ?, ?)",
                           (nombre, cuit, razon_social))
            conn.commit()
            cliente_id = cursor.lastrowid
            print(f"✅ Cliente '{nombre}' registrado con éxito.")
        except sqlite3.IntegrityError:
            print(f"Error: Ya existe un cliente con el nombre '{nombre}'.")
            cliente_id = None
        except Exception as e:
            print(f"Error al registrar cliente: {e}")
            cliente_id = None

    conn.close()
    return cliente_id


def guardar_comprobante(nro_operacion, fecha, importe, cuenta, cliente_id):
    """Guarda un comprobante en la base de datos si el número de operación no existe."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM comprobantes WHERE nro_operacion = ?", (nro_operacion,))
    comprobante_existente = cursor.fetchone()

    if comprobante_existente:
        print(f"❌ Error: El comprobante con número de operación '{nro_operacion}' ya existe.")
        conn.close()
        return False
    else:
        try:
            cursor.execute("INSERT INTO comprobantes (nro_operacion, fecha, importe, cuenta, cliente_id) VALUES (?, ?, ?, ?, ?)",
                           (nro_operacion, fecha, importe, cuenta, cliente_id))
            conn.commit()
            print(f"✅ Comprobante '{nro_operacion}' guardado con éxito.")
            conn.close()
            return True
        except Exception as e:
            print(f"Error al guardar el comprobante: {e}")
            conn.close()
            return False


# --- 2. Funciones de Extracción de Datos (OCR) ---

def extraer_datos_comprobante(ruta_archivo):
    """
    Extrae texto de PDF o imagen y busca patrones de datos.
    NOTA: La extracción por patrones es básica. Necesitarás ajustar
    las expresiones regulares para que coincidan con el formato de tus documentos.
    """
    if not os.path.exists(ruta_archivo):
        print(f"❌ Error: El archivo '{ruta_archivo}' no existe.")
        return None

    texto_extraido = ""
    try:
        if ruta_archivo.lower().endswith(('.png', '.jpg', '.jpeg')):
            img = Image.open(ruta_archivo)
            texto_extraido = pytesseract.image_to_string(img, lang='spa')
        elif ruta_archivo.lower().endswith('.pdf'):
            import fitz # Importar PyMuPDF aquí para no forzar su instalación si solo se usa imagen
            documento = fitz.open(ruta_archivo)
            for pagina_num in range(documento.page_count):
                pagina = documento.load_page(pagina_num)
                texto_extraido += pagina.get_text()
            documento.close()
        else:
            print("Formato de archivo no soportado. Por favor, usá PDF, PNG, JPG o JPEG.")
            return None
    except pytesseract.TesseractNotFoundError:
        print("❌ Error: Tesseract OCR no está instalado o no se encuentra en tu PATH.")
        print("Por favor, instala Tesseract y/o configura 'pytesseract.pytesseract.tesseract_cmd' en el código.")
        return None
    except Exception as e:
        print(f"❌ Error al procesar el archivo '{ruta_archivo}': {e}")
        return None

    print("\n--- Texto extraído del comprobante ---")
    print(texto_extraido)
    print("--------------------------------------\n")

    # --- EXPRESIONES REGULARES ---
    nro_operacion = re.search(r'(?:Nro\.?\s*Operación|No\.?\s*Operación|Operacion|Op\.?|Nº Operación):\s*(\S+)', texto_extraido, re.IGNORECASE)
    fecha = re.search(r'Fecha:\s*(\d{2}[-/]\d{2}[-/]\d{4})', texto_extraido, re.IGNORECASE)
    importe = re.search(r'(?:Importe|Total|Monto):\s*[$€]?\s*([\d\.,]+)', texto_extraido, re.IGNORECASE)
    cuenta = re.search(r'(?:Cuenta|Cta|Destino):\s*(\S+)', texto_extraido, re.IGNORECASE)

    importe_valor = None
    if importe:
        try:
            importe_str = importe.group(1).replace('.', '').replace(',', '.')
            importe_valor = float(importe_str)
        except ValueError:
            print(f"Advertencia: No se pudo convertir el importe '{importe.group(1)}' a número.")
            importe_valor = None

    datos = {
        "nro_operacion": nro_operacion.group(1) if nro_operacion else None,
        "fecha": fecha.group(1) if fecha else None,
        "importe": importe_valor,
        "cuenta": cuenta.group(1) if cuenta else None
    }
    return datos


# --- 2.1. Funciones de Gestión de Productos ---

def agregar_producto():
    """Permite añadir un nuevo producto al inventario."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()
    
    codigo = input("Ingrese el código del producto (ej: SKU-001): ").strip().upper()
    descripcion = input("Ingrese la descripción del producto: ").strip()
    
    while True:
        try:
            stock = int(input("Ingrese el stock inicial disponible: "))
            if stock < 0:
                print("El stock no puede ser negativo.")
                continue
            break
        except ValueError:
            print("Por favor, ingrese un número entero para el stock.")

    # Las columnas de precios se inicializarán a 0.0 si no se especifican.
    # Si quieres pedir precios aquí, deberías agregar más inputs.
    try:
        cursor.execute("INSERT INTO productos (codigo, descripcion, stock_disponible) VALUES (?, ?, ?)",
                       (codigo, descripcion, stock))
        conn.commit()
        print(f"✅ Producto '{descripcion}' ({codigo}) agregado con {stock} unidades en stock.")
    except sqlite3.IntegrityError:
        print(f"❌ Error: Ya existe un producto con el código '{codigo}'.")
    except Exception as e:
        print(f"❌ Error al agregar producto: {e}")
    finally:
        conn.close()

def ver_productos():
    """Muestra la lista completa de productos con su stock y estado."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()
    # Ahora seleccionamos también las columnas de precios para mostrar
    cursor.execute("SELECT codigo, descripcion, stock_disponible, stock_reservado, estado_producto, precio_1 FROM productos ORDER BY codigo")
    productos = cursor.fetchall()
    conn.close()

    if not productos:
        print("\nNo hay productos registrados en el inventario.")
        return

    print("\n--- Listado de Productos en Inventario ---")
    print(f"{'Código':<15} {'Descripción':<30} {'Disp.':<8} {'Res.':<8} {'Estado':<15} {'Precio (1)':<10}")
    print("-" * 86)
    for prod in productos:
        print(f"{prod[0]:<15} {prod[1]:<30} {prod[2]:<8} {prod[3]:<8} {prod[4]:<15} {prod[5]:<10.2f}")
    print("-" * 86)

def modificar_stock_producto():
    """Permite ajustar el stock disponible de un producto existente."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    codigo = input("Ingrese el código del producto a modificar: ").strip().upper()
    
    cursor.execute("SELECT id, descripcion, stock_disponible, stock_reservado FROM productos WHERE codigo = ?", (codigo,))
    producto = cursor.fetchone()

    if not producto:
        print(f"❌ Error: Producto con código '{codigo}' no encontrado.")
        conn.close()
        return

    prod_id, descripcion, stock_actual_disponible, stock_actual_reservado = producto
    print(f"\nProducto: {descripcion} (Código: {codigo})")
    print(f"Stock Disponible Actual: {stock_actual_disponible}")
    print(f"Stock Reservado Actual: {stock_actual_reservado}")

    while True:
        try:
            cambio_stock = int(input("Ingrese la cantidad a SUMAR (+) o RESTAR (-) al stock disponible: "))
            break
        except ValueError:
            print("Por favor, ingrese un número entero.")

    nuevo_stock_disponible = stock_actual_disponible + cambio_stock

    if nuevo_stock_disponible < 0:
        print("⚠️ Advertencia: El stock disponible no puede ser negativo. Ajuste no realizado.")
        conn.close()
        return

    try:
        cursor.execute("UPDATE productos SET stock_disponible = ? WHERE id = ?",
                       (nuevo_stock_disponible, prod_id))
        conn.commit()
        print(f"✅ Stock de '{descripcion}' ({codigo}) actualizado.")
        print(f"Nuevo Stock Disponible: {nuevo_stock_disponible}")
        actualizar_estado_producto_automatico(prod_id, nuevo_stock_disponible, stock_actual_reservado)

    except Exception as e:
        print(f"❌ Error al modificar stock: {e}")
    finally:
        conn.close()

def actualizar_estado_producto_automatico(producto_id, stock_disponible, stock_reservado):
    """Actualiza el estado_producto basado en stock (ej: sin_stock)."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()
    
    nuevo_estado = 'disponible'
    if stock_disponible == 0 and stock_reservado == 0:
        nuevo_estado = 'sin_stock'
    elif stock_disponible == 0 and stock_reservado > 0:
        nuevo_estado = 'reservado'
    
    cursor.execute("UPDATE productos SET estado_producto = ? WHERE id = ?", (nuevo_estado, producto_id))
    conn.commit()
    conn.close()
    
    print(f"Estado de producto actualizado a '{nuevo_estado}'.")

def cambiar_estado_producto_manual():
    """Permite cambiar manualmente el estado de un producto (ej: discontinuado)."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    codigo = input("Ingrese el código del producto para cambiar su estado: ").strip().upper()
    cursor.execute("SELECT id, descripcion, estado_producto FROM productos WHERE codigo = ?", (codigo,))
    producto = cursor.fetchone()

    if not producto:
        print(f"❌ Error: Producto con código '{codigo}' no encontrado.")
        conn.close()
        return

    prod_id, descripcion, estado_actual = producto
    print(f"\nProducto: {descripcion} (Código: {codigo}) - Estado actual: {estado_actual}")
    print("Opciones de estado: disponible, discontinuado, en_transito, pedida, sin_stock")
    nuevo_estado = input("Ingrese el nuevo estado: ").strip().lower()

    if nuevo_estado not in ['disponible', 'discontinuado', 'en_transito', 'pedida', 'sin_stock']:
        print("❌ Estado inválido. Por favor, elija uno de la lista.")
        conn.close()
        return

    try:
        cursor.execute("UPDATE productos SET estado_producto = ? WHERE id = ?",
                       (nuevo_estado, prod_id))
        conn.commit()
        print(f"✅ Estado de '{descripcion}' ({codigo}) cambiado a '{nuevo_estado}'.")
    except Exception as e:
        print(f"❌ Error al cambiar estado del producto: {e}")
    finally:
        conn.close()


# --- 2.2. Funciones de Gestión de Notas de Pedido ---

def crear_nota_pedido():
    """Permite crear una nueva nota de pedido, seleccionando productos y gestionando el tipo de entrega."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    nombre_cliente = input("Ingrese el nombre del cliente para la nota de pedido: ").strip()
    cliente_id = obtener_o_crear_cliente(nombre_cliente)

    if not cliente_id:
        print("No se pudo identificar al cliente. Abortando creación de nota de pedido.")
        conn.close()
        return

    print("\n--- Productos para la Nota de Pedido ---")
    detalle_pedido_temp = []

    while True:
        ver_productos() # Muestra los productos disponibles (incluyendo precios ahora)
        codigo_producto = input("Ingrese el código del producto a agregar (o 'FIN' para terminar de agregar productos): ").strip().upper()
        if codigo_producto == 'FIN':
            break

        # Seleccionamos también los precios para que estén disponibles
        cursor.execute("SELECT id, descripcion, stock_disponible, stock_reservado, estado_producto, precio_1 FROM productos WHERE codigo = ?", (codigo_producto,))
        producto = cursor.fetchone()

        if not producto:
            print(f"❌ Producto con código '{codigo_producto}' no encontrado.")
            continue

        prod_id, descripcion, stock_disponible, stock_reservado, estado_producto, precio_default = producto
        print(f"Producto seleccionado: {descripcion} | Stock Disponible: {stock_disponible} | Stock Reservado: {stock_reservado} | Estado: {estado_producto} | Precio sugerido: {precio_default:.2f}")

        if stock_disponible <= 0 and estado_producto not in ('en_transito', 'pedida'):
             print("⚠️ Advertencia: Este producto no tiene stock disponible para venta inmediata.")
             confirmar_sin_stock = input("¿Desea agregar de todos modos? (s/n): ").lower()
             if confirmar_sin_stock != 's':
                 continue

        while True:
            try:
                cantidad = int(input(f"Ingrese la cantidad de '{descripcion}' a pedir: "))
                if cantidad <= 0:
                    print("La cantidad debe ser mayor a 0.")
                    continue
                if cantidad > (stock_disponible - stock_reservado) and stock_disponible > 0:
                    print(f"⚠️ ALERTA: La cantidad solicitada ({cantidad}) excede el stock real no reservado ({stock_disponible - stock_reservado}).")
                    confirmar_exceso = input("¿Confirmar pedido con esta cantidad a pesar de la alerta? (s/n): ").lower()
                    if confirmar_exceso != 's':
                        break
                break
            except ValueError:
                print("Por favor, ingrese un número entero para la cantidad.")
        else: # Este 'else' se ejecuta si el 'while True' de la cantidad se rompió por 'n'
            continue # Vuelve al inicio del while de productos

        while True:
            try:
                # Sugerir el precio por defecto, pero permitir modificarlo
                precio_input = input(f"Ingrese el precio unitario de '{descripcion}' (sugerido {precio_default:.2f}): ").strip()
                if not precio_input: # Si el usuario no ingresa nada, usa el sugerido
                    precio_unitario = precio_default
                else:
                    precio_unitario = float(precio_input.replace(',', '.'))
                
                if precio_unitario <= 0:
                    print("El precio debe ser mayor a 0.")
                    continue
                break
            except ValueError:
                print("Por favor, ingrese un número válido para el precio.")

        detalle_pedido_temp.append((prod_id, cantidad, precio_unitario))
        print(f"'{descripcion}' ({cantidad} unidades) agregado al pedido temporal.")

    if not detalle_pedido_temp:
        print("No se agregaron productos al pedido. Abortando creación de nota de pedido.")
        conn.close()
        return

    tipo_entrega = "Retiro por mostrador"
    direccion_envio = None
    telefono_contacto = None

    opcion_entrega = input("\n¿El pedido es para 'Retiro por mostrador' o 'Envío'? (mostrador/envio): ").strip().lower()
    if opcion_entrega == 'envio':
        tipo_entrega = "Pedido para envio"
        direccion_envio = input("Ingrese la dirección de envío: ").strip()
        telefono_contacto = input("Ingrese el teléfono de contacto del cliente para el envío: ").strip()
    
    fecha_creacion = datetime.date.today().isoformat()

    try:
        cursor.execute("""
            INSERT INTO notas_pedido (cliente_id, fecha_creacion, tipo_entrega, direccion_envio, telefono_contacto, estado)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cliente_id, fecha_creacion, tipo_entrega, direccion_envio, telefono_contacto, 'pendiente'))
        nota_pedido_id = cursor.lastrowid
        print(f"\n✅ Nota de Pedido #{nota_pedido_id} creada como 'pendiente'.")

        for prod_id, cantidad, precio_unitario in detalle_pedido_temp:
            cursor.execute("""
                INSERT INTO detalle_pedido (nota_pedido_id, producto_id, cantidad, precio_unitario)
                VALUES (?, ?, ?, ?)
            """, (nota_pedido_id, prod_id, cantidad, precio_unitario))
        
        conn.commit()
        print("✅ Detalles del pedido guardados.")

    except Exception as e:
        print(f"❌ Error al guardar la Nota de Pedido o sus detalles: {e}")
        conn.rollback()
    finally:
        conn.close()

def ver_notas_pedido(filtrar_expedicion=False):
    """
    Muestra las notas de pedido.
    Si filtrar_expedicion es True, solo muestra pedidos 'pendiente' y 'aprobada'.
    """
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    query = """
    SELECT 
        np.id, c.nombre, np.fecha_creacion, np.tipo_entrega, np.direccion_envio, 
        np.telefono_contacto, np.estado, SUM(dp.cantidad * dp.precio_unitario) AS total
    FROM 
        notas_pedido np
    JOIN 
        clientes c ON np.cliente_id = c.id
    JOIN
        detalle_pedido dp ON np.id = dp.nota_pedido_id
    """
    params = []
    
    if filtrar_expedicion:
        query += " WHERE np.estado IN ('pendiente', 'aprobada')"
    
    query += " GROUP BY np.id ORDER BY np.fecha_creacion DESC, np.id DESC"

    cursor.execute(query, params)
    notas = cursor.fetchall()
    conn.close()

    if not notas:
        if filtrar_expedicion:
            print("\nNo hay notas de pedido 'pendientes' o 'aprobadas' para Expedición.")
        else:
            print("\nNo hay notas de pedido registradas.")
        return

    print(f"\n--- Listado de Notas de Pedido ({'Para Expedición' if filtrar_expedicion else 'Todas'}) ---")
    print(f"{'ID':<4} {'Cliente':<20} {'Fecha':<12} {'Entrega':<15} {'Estado':<10} {'Total':<10} {'Contacto/Dirección':<30}")
    print("-" * 110)
    for nota in notas:
        estado = nota[6]
        if estado == 'aprobada':
            estado_visual = f"🟢 {estado}"
        elif estado == 'pendiente':
            estado_visual = f"🟡 {estado}"
        elif estado == 'entregada':
            estado_visual = f"🔴 {estado}"
        else:
            estado_visual = f"⚫ {estado}"

        contacto_info = ""
        if nota[3] == 'Pedido para envio':
            contacto_info = f"Tel: {nota[5] or 'N/A'}, Dir: {nota[4] or 'N/A'}"
        else:
            contacto_info = "Retiro en mostrador"
            
        print(f"{nota[0]:<4} {nota[1]:<20} {nota[2]:<12} {nota[3]:<15} {estado_visual:<10} {nota[7]:<10.2f} {contacto_info:<30}")
    print("-" * 110)

    while True:
        ver_detalles = input("\n¿Desea ver los detalles de una nota de pedido específica? (s/n): ").lower()
        if ver_detalles != 's':
            break
        
        try:
            id_nota = int(input("Ingrese el ID de la nota de pedido para ver detalles: "))
            mostrar_detalle_nota_pedido(id_nota)
        except ValueError:
            print("Por favor, ingrese un ID válido.")

def mostrar_detalle_nota_pedido(nota_pedido_id):
    """Muestra los productos y detalles específicos de una nota de pedido."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            np.id, c.nombre, np.fecha_creacion, np.tipo_entrega, np.direccion_envio, 
            np.telefono_contacto, np.estado
        FROM 
            notas_pedido np
        JOIN 
            clientes c ON np.cliente_id = c.id
        WHERE np.id = ?
    """, (nota_pedido_id,))
    nota = cursor.fetchone()

    if not nota:
        print(f"Nota de Pedido con ID {nota_pedido_id} no encontrada.")
        conn.close()
        return

    print(f"\n--- Detalles de Nota de Pedido #{nota[0]} ---")
    print(f"Cliente: {nota[1]}")
    print(f"Fecha de Creación: {nota[2]}")
    print(f"Tipo de Entrega: {nota[3]}")
    if nota[3] == 'Pedido para envio':
        print(f"Dirección de Envío: {nota[4] or 'N/A'}")
        print(f"Teléfono Contacto: {nota[5] or 'N/A'}")
    print(f"Estado: {nota[6]}")
    print("\nProductos:")
    print(f"{'Código':<15} {'Descripción':<30} {'Cantidad':<10} {'P. Unit.':<10} {'Subtotal':<10}")
    print("-" * 80)

    cursor.execute("""
        SELECT 
            p.codigo, p.descripcion, dp.cantidad, dp.precio_unitario
        FROM 
            detalle_pedido dp
        JOIN 
            productos p ON dp.producto_id = p.id
        WHERE dp.nota_pedido_id = ?
    """, (nota_pedido_id,))
    detalles = cursor.fetchall()
    
    total_pedido = 0
    for det in detalles:
        subtotal = det[2] * det[3]
        total_pedido += subtotal
        print(f"{det[0]:<15} {det[1]:<30} {det[2]:<10} {det[3]:<10.2f} {subtotal:<10.2f}")
    print("-" * 80)
    print(f"{'TOTAL PEDIDO:':<66} {total_pedido:<10.2f}")
    conn.close()

def actualizar_estado_nota_pedido():
    """
    Permite cambiar el estado de una nota de pedido y ajusta el stock reservado/disponible.
    Estados: pendiente, aprobada, entregada, cancelada.
    """
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    id_nota = input("Ingrese el ID de la nota de pedido a actualizar: ").strip()
    try:
        id_nota = int(id_nota)
    except ValueError:
        print("❌ ID de nota de pedido inválido. Debe ser un número.")
        conn.close()
        return

    cursor.execute("SELECT estado FROM notas_pedido WHERE id = ?", (id_nota,))
    nota_actual = cursor.fetchone()

    if not nota_actual:
        print(f"❌ Nota de pedido con ID {id_nota} no encontrada.")
        conn.close()
        return

    estado_actual = nota_actual[0]
    print(f"Estado actual de la Nota de Pedido #{id_nota}: {estado_actual}")
    print("Nuevos estados posibles: pendiente, aprobada, entregada, cancelada")
    nuevo_estado = input("Ingrese el nuevo estado: ").strip().lower()

    if nuevo_estado not in ['pendiente', 'aprobada', 'entregada', 'cancelada']:
        print("❌ Estado inválido. Por favor, elija uno de la lista.")
        conn.close()
        return
    
    if nuevo_estado == estado_actual:
        print("El estado es el mismo. No se realizaron cambios.")
        conn.close()
        return

    cursor.execute("SELECT producto_id, cantidad FROM detalle_pedido WHERE nota_pedido_id = ?", (id_nota,))
    detalles = cursor.fetchall()

    try:
        if estado_actual == 'pendiente' and nuevo_estado == 'aprobada':
            for prod_id, cantidad in detalles:
                cursor.execute("UPDATE productos SET stock_disponible = stock_disponible - ?, stock_reservado = stock_reservado + ? WHERE id = ?",
                               (cantidad, cantidad, prod_id))
            print(f"✅ Mercadería para Nota de Pedido #{id_nota} RESERVADA.")
        
        elif estado_actual == 'aprobada' and nuevo_estado == 'entregada':
            for prod_id, cantidad in detalles:
                cursor.execute("UPDATE productos SET stock_reservado = stock_reservado - ? WHERE id = ?",
                               (cantidad, prod_id))
            print(f"✅ Mercadería para Nota de Pedido #{id_nota} ENTREGADA y stock ajustado.")
        
        elif nuevo_estado == 'cancelada' and estado_actual != 'entregada':
            for prod_id, cantidad in detalles:
                cursor.execute("UPDATE productos SET stock_disponible = stock_disponible + ?, stock_reservado = stock_reservado - ? WHERE id = ?",
                               (cantidad, cantidad, prod_id))
            print(f"✅ Nota de Pedido #{id_nota} CANCELADA y stock liberado.")
        
        elif estado_actual == 'pendiente' and nuevo_estado == 'entregada':
             print("⚠️ Advertencia: Un pedido pendiente no debería pasar directamente a entregado sin antes ser aprobado y reservar stock.")
             confirm = input("¿Confirmar salto de estado y descontar directamente de disponible? (s/n): ").lower()
             if confirm == 's':
                for prod_id, cantidad in detalles:
                    cursor.execute("UPDATE productos SET stock_disponible = stock_disponible - ? WHERE id = ?", (cantidad, prod_id))
                print(f"✅ Nota de Pedido #{id_nota} entregada directamente y stock descontado de disponible.")
             else:
                print("Operación cancelada. El estado no se actualizó.")
                conn.close()
                return

        cursor.execute("UPDATE notas_pedido SET estado = ? WHERE id = ?", (nuevo_estado, id_nota))
        conn.commit()
        print(f"✅ Estado de Nota de Pedido #{id_nota} actualizado a '{nuevo_estado}'.")

    except Exception as e:
        print(f"❌ Error al actualizar estado o ajustar stock: {e}")
        conn.rollback()
    finally:
        conn.close()


# --- 2.3. Funciones de Gestión de Presupuestos ---

def crear_presupuesto():
    """Permite crear un nuevo presupuesto, seleccionando productos."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    nombre_cliente = input("Ingrese el nombre del cliente para el presupuesto: ").strip()
    cliente_id = obtener_o_crear_cliente(nombre_cliente)

    if not cliente_id:
        print("No se pudo identificar al cliente. Abortando creación de presupuesto.")
        conn.close()
        return

    print("\n--- Productos para el Presupuesto ---")
    detalle_presupuesto_temp = []

    while True:
        ver_productos() # Muestra los productos disponibles (incluyendo precios)
        codigo_producto = input("Ingrese el código del producto a agregar (o 'FIN' para terminar): ").strip().upper()
        if codigo_producto == 'FIN':
            break

        # Seleccionamos también los precios para que estén disponibles
        cursor.execute("SELECT id, descripcion, precio_1 FROM productos WHERE codigo = ?", (codigo_producto,))
        producto = cursor.fetchone()

        if not producto:
            print(f"❌ Producto con código '{codigo_producto}' no encontrado.")
            continue

        prod_id, descripcion, precio_default = producto # Solo tomamos el precio_1 como sugerencia
        
        while True:
            try:
                cantidad = int(input(f"Ingrese la cantidad de '{descripcion}' para el presupuesto: "))
                if cantidad <= 0:
                    print("La cantidad debe ser mayor a 0.")
                    continue
                break
            except ValueError:
                print("Por favor, ingrese un número entero para la cantidad.")

        while True:
            try:
                # Sugerir el precio por defecto, pero permitir modificarlo
                precio_input = input(f"Ingrese el precio unitario de '{descripcion}' (sugerido {precio_default:.2f}): ").strip()
                if not precio_input: # Si el usuario no ingresa nada, usa el sugerido
                    precio_unitario = precio_default
                else:
                    precio_unitario = float(precio_input.replace(',', '.'))

                if precio_unitario <= 0:
                    print("El precio debe ser mayor a 0.")
                    continue
                break
            except ValueError:
                print("Por favor, ingrese un número válido para el precio.")

        detalle_presupuesto_temp.append((prod_id, cantidad, precio_unitario))
        print(f"'{descripcion}' ({cantidad} unidades) agregado al presupuesto temporal.")

    if not detalle_presupuesto_temp:
        print("No se agregaron productos al presupuesto. Abortando creación.")
        conn.close()
        return

    fecha_creacion = datetime.date.today().isoformat()

    try:
        cursor.execute("""
            INSERT INTO presupuestos (cliente_id, fecha_creacion, estado)
            VALUES (?, ?, ?)
        """, (cliente_id, fecha_creacion, 'borrador'))
        presupuesto_id = cursor.lastrowid
        print(f"\n✅ Presupuesto #{presupuesto_id} creado como 'borrador'.")

        for prod_id, cantidad, precio_unitario in detalle_presupuesto_temp:
            cursor.execute("""
                INSERT INTO detalle_presupuesto (presupuesto_id, producto_id, cantidad, precio_unitario)
                VALUES (?, ?, ?, ?)
            """, (presupuesto_id, prod_id, cantidad, precio_unitario))
        
        conn.commit()
        print("✅ Detalles del presupuesto guardados.")

    except Exception as e:
        print(f"❌ Error al guardar el Presupuesto o sus detalles: {e}")
        conn.rollback()
    finally:
        conn.close()


def ver_presupuestos():
    """Muestra la lista completa de presupuestos con su estado."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    query = """
    SELECT
        p.id, c.nombre, p.fecha_creacion, p.estado, SUM(dp.cantidad * dp.precio_unitario) AS total
    FROM
        presupuestos p
    JOIN
        clientes c ON p.cliente_id = c.id
    JOIN
        detalle_presupuesto dp ON p.id = dp.presupuesto_id
    GROUP BY p.id
    ORDER BY p.fecha_creacion DESC, p.id DESC
    """
    cursor.execute(query)
    presupuestos = cursor.fetchall()
    conn.close()

    if not presupuestos:
        print("\nNo hay presupuestos registrados.")
        return

    print("\n--- Listado de Presupuestos ---")
    print(f"{'ID':<4} {'Cliente':<20} {'Fecha':<12} {'Estado':<12} {'Total':<10}")
    print("-" * 60)
    for pres in presupuestos:
        estado = pres[3]
        if estado == 'aprobado':
            estado_visual = f"🔵 {estado}"
        elif estado == 'facturado':
            estado_visual = f"🟣 {estado}"
        elif estado == 'borrador':
            estado_visual = f"⚪ {estado}"
        else: # rechazado
            estado_visual = f"⚫ {estado}"

        print(f"{pres[0]:<4} {pres[1]:<20} {pres[2]:<12} {estado_visual:<12} {pres[4]:<10.2f}")
    print("-" * 60)

    while True:
        ver_detalles = input("\n¿Desea ver los detalles de un presupuesto específico? (s/n): ").lower()
        if ver_detalles != 's':
            break
        
        try:
            id_presupuesto = int(input("Ingrese el ID del presupuesto para ver detalles: "))
            mostrar_detalle_presupuesto(id_presupuesto)
        except ValueError:
            print("Por favor, ingrese un ID válido.")

def mostrar_detalle_presupuesto(presupuesto_id):
    """Muestra los productos y detalles específicos de un presupuesto."""
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            p.id, c.nombre, p.fecha_creacion, p.estado
        FROM 
            presupuestos p
        JOIN 
            clientes c ON p.cliente_id = c.id
        WHERE p.id = ?
    """, (presupuesto_id,))
    presupuesto = cursor.fetchone()

    if not presupuesto:
        print(f"Presupuesto con ID {presupuesto_id} no encontrado.")
        conn.close()
        return

    print(f"\n--- Detalles de Presupuesto #{presupuesto[0]} ---")
    print(f"Cliente: {presupuesto[1]}")
    print(f"Fecha de Creación: {presupuesto[2]}")
    print(f"Estado: {presupuesto[3]}")
    print("\nProductos:")
    print(f"{'Código':<15} {'Descripción':<30} {'Cantidad':<10} {'P. Unit.':<10} {'Subtotal':<10}")
    print("-" * 80)

    cursor.execute("""
        SELECT 
            prod.codigo, prod.descripcion, dp.cantidad, dp.precio_unitario
        FROM 
            detalle_presupuesto dp
        JOIN 
            productos prod ON dp.producto_id = prod.id
        WHERE dp.presupuesto_id = ?
    """, (presupuesto_id,))
    detalles = cursor.fetchall()
    
    total_presupuesto = 0
    for det in detalles:
        subtotal = det[2] * det[3]
        total_presupuesto += subtotal
        print(f"{det[0]:<15} {det[1]:<30} {det[2]:<10} {det[3]:<10.2f} {subtotal:<10.2f}")
    print("-" * 80)
    print(f"{'TOTAL PRESUPUESTO:':<66} {total_presupuesto:<10.2f}")
    conn.close()


def actualizar_estado_presupuesto():
    """
    Permite cambiar el estado de un presupuesto.
    Estados: borrador, aprobado, facturado, rechazado.
    """
    conn = sqlite3.connect('presupuestos.db')
    cursor = conn.cursor()

    id_presupuesto = input("Ingrese el ID del presupuesto a actualizar: ").strip()
    try:
        id_presupuesto = int(id_presupuesto)
    except ValueError:
        print("❌ ID de presupuesto inválido. Debe ser un número.")
        conn.close()
        return

    cursor.execute("SELECT estado FROM presupuestos WHERE id = ?", (id_presupuesto,))
    presupuesto_actual = cursor.fetchone()

    if not presupuesto_actual:
        print(f"❌ Presupuesto con ID {id_presupuesto} no encontrado.")
        conn.close()
        return

    estado_actual = presupuesto_actual[0]
    print(f"Estado actual del Presupuesto #{id_presupuesto}: {estado_actual}")
    print("Nuevos estados posibles: borrador, aprobado, facturado, rechazado")
    nuevo_estado = input("Ingrese el nuevo estado: ").strip().lower()

    if nuevo_estado not in ['borrador', 'aprobado', 'facturado', 'rechazado']:
        print("❌ Estado inválido. Por favor, elija uno de la lista.")
        conn.close()
        return
    
    if nuevo_estado == estado_actual:
        print("El estado es el mismo. No se realizaron cambios.")
        conn.close()
        return

    try:
        if nuevo_estado == 'facturado' and estado_actual != 'facturado':
            print("\nEste presupuesto se marcará como 'Facturado'.")
            confirmar_facturar = input("¿Desea crear una Nota de Pedido a partir de este presupuesto? (s/n): ").lower()
            if confirmar_facturar == 's':
                cursor.execute("""
                    SELECT cliente_id FROM presupuestos WHERE id = ?
                """, (id_presupuesto,))
                cliente_id = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT producto_id, cantidad, precio_unitario
                    FROM detalle_presupuesto WHERE presupuesto_id = ?
                """, (id_presupuesto,))
                detalles_presupuesto = cursor.fetchall()

                if not detalles_presupuesto:
                    print("No hay productos en este presupuesto para crear una Nota de Pedido.")
                    conn.close()
                    return

                fecha_creacion_np = datetime.date.today().isoformat()
                cursor.execute("""
                    INSERT INTO notas_pedido (cliente_id, fecha_creacion, tipo_entrega, estado)
                    VALUES (?, ?, ?, ?)
                """, (cliente_id, fecha_creacion_np, 'Retiro por mostrador', 'pendiente'))
                id_nueva_nota_pedido = cursor.lastrowid
                
                for prod_id, cantidad, precio_unitario in detalles_presupuesto:
                    cursor.execute("""
                        INSERT INTO detalle_pedido (nota_pedido_id, producto_id, cantidad, precio_unitario)
                        VALUES (?, ?, ?, ?)
                    """, (id_nueva_nota_pedido, prod_id, cantidad, precio_unitario))
                
                print(f"✅ Se ha creado la Nota de Pedido #{id_nueva_nota_pedido} a partir de este presupuesto.")
                print("Recuerde ir al módulo de Notas de Pedido para gestionar su estado y el stock.")
                
                sincronizar_a_google_sheets(modulo='pedidos')
            else:
                print("No se creó Nota de Pedido. El presupuesto solo cambiará a 'Facturado'.")

        cursor.execute("UPDATE presupuestos SET estado = ? WHERE id = ?", (nuevo_estado, id_presupuesto))
        conn.commit()
        print(f"✅ Estado de Presupuesto #{id_presupuesto} actualizado a '{nuevo_estado}'.")

    except Exception as e:
        print(f"❌ Error al actualizar estado del presupuesto: {e}")
        conn.rollback()
    finally:
        conn.close()


# --- 3. Funciones de Sincronización con Google Sheets ---

SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

def get_google_sheet_client():
    """Obtiene un cliente de gspread autenticado."""
    try:
        gc = gspread.oauth(credentials_filename='credentials.json', authorized_user_filename='token.json', scopes=SCOPES)
        return gc
    except Exception as e:
        print(f"❌ Error al autenticar con Google Sheets: {e}")
        print("Asegúrate de que 'credentials.json' esté en la misma carpeta que el script.")
        print("La primera vez, se abrirá una ventana del navegador para que inicies sesión y autorices.")
        return None

def sincronizar_a_google_sheets(modulo=None, nombre_hoja_calculo="Comprobantes App Data"):
    """
    Sincroniza datos específicos de la base de datos SQLite a una pestaña de Google Sheets.
    El parámetro 'modulo' indica qué datos sincronizar ('comprobantes', 'productos', 'pedidos', 'presupuestos').
    """
    gc = get_google_sheet_client()
    if not gc:
        return

    try:
        spreadsheet = gc.open(nombre_hoja_calculo)
        print(f"✅ Hoja de cálculo '{nombre_hoja_calculo}' abierta.")

        conn = sqlite3.connect('presupuestos.db') # Conexión a la DB unificada
        df = pd.DataFrame()
        nombre_pestana = ""

        if modulo == 'comprobantes':
            nombre_pestana = "Comprobantes"
            query = """
            SELECT
                c.nombre AS Nombre_Cliente,
                c.cuit AS CUIT_Cliente,
                c.razon_social AS Razon_Social_Cliente,
                comp.nro_operacion AS Numero_Operacion,
                comp.fecha AS Fecha_Comprobante,
                comp.importe AS Importe_Comprobante,
                comp.cuenta AS Cuenta_Destino
            FROM
                comprobantes comp
            JOIN
                clientes c ON comp.cliente_id = c.id
            ORDER BY comp.id ASC
            """
            df = pd.read_sql_query(query, conn)
        
        elif modulo == 'productos':
            nombre_pestana = "Productos"
            query = """
            SELECT
                codigo AS Codigo_Producto,
                descripcion AS Descripcion,
                stock_disponible AS Stock_Disponible,
                stock_reservado AS Stock_Reservado,
                estado_producto AS Estado,
                costo_base AS Costo_Base,
                precio_0_1 AS Precio_0_1,
                precio_1 AS Precio_1,
                precio_5 AS Precio_5,
                precio_10 AS Precio_10,
                precio_25 AS Precio_25,
                precio_tambor_rollo AS Precio_Tambor_Rollo
            FROM
                productos
            ORDER BY codigo ASC
            """
            df = pd.read_sql_query(query, conn)

        elif modulo == 'pedidos':
            nombre_pestana = "Notas_Pedido"
            query = """
            SELECT
                np.id AS ID_Pedido,
                c.nombre AS Cliente,
                np.fecha_creacion AS Fecha_Creacion,
                np.tipo_entrega AS Tipo_Entrega,
                np.direccion_envio AS Direccion_Envio,
                np.telefono_contacto AS Telefono_Contacto,
                np.estado AS Estado_Pedido,
                SUM(dp.cantidad * dp.precio_unitario) AS Total_Pedido
            FROM
                notas_pedido np
            JOIN
                clientes c ON np.cliente_id = c.id
            JOIN
                detalle_pedido dp ON np.id = dp.nota_pedido_id
            GROUP BY np.id
            ORDER BY np.fecha_creacion DESC, np.id DESC
            """
            df = pd.read_sql_query(query, conn)
        
        elif modulo == 'presupuestos':
            nombre_pestana = "Presupuestos"
            query = """
            SELECT
                p.id AS ID_Presupuesto,
                c.nombre AS Cliente,
                p.fecha_creacion AS Fecha_Creacion,
                p.estado AS Estado_Presupuesto,
                SUM(dp.cantidad * dp.precio_unitario) AS Total_Presupuesto
            FROM
                presupuestos p
            JOIN
                clientes c ON p.cliente_id = c.id
            JOIN
                detalle_presupuesto dp ON p.id = dp.presupuesto_id
            GROUP BY p.id
            ORDER BY p.fecha_creacion DESC, p.id DESC
            """
            df = pd.read_sql_query(query, conn)

        else:
            print("❌ Módulo de sincronización no especificado o inválido.")
            conn.close()
            return

        conn.close()

        try:
            worksheet = spreadsheet.worksheet(nombre_pestana)
            print(f"✅ Pestaña '{nombre_pestana}' encontrada.")
        except gspread.exceptions.WorksheetNotFound:
            print(f"Pestaña '{nombre_pestana}' no encontrada. Creando nueva pestaña...")
            worksheet = spreadsheet.add_worksheet(title=nombre_pestana, rows="100", cols="20")
            print(f"✅ Pestaña '{nombre_pestana}' creada con éxito.")

        if df.empty:
            print(f"No hay datos en la base de datos para sincronizar en el módulo '{modulo}'.")
            worksheet.clear()
            return

        datos_para_sheets = [df.columns.tolist()] + df.values.tolist()

        worksheet.clear()
        worksheet.update(datos_para_sheets)
        print(f"✅ Datos del módulo '{modulo}' sincronizados con éxito en Google Sheets: '{nombre_hoja_calculo}' -> Pestaña '{nombre_pestana}'.")

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"❌ Error: Hoja de cálculo '{nombre_hoja_calculo}' no encontrada en tu Google Drive.")
        print("Asegúrate de que el nombre sea exacto y que tengas permisos.")
    except Exception as e:
        print(f"❌ Error al sincronizar con Google Sheets: {e}")

