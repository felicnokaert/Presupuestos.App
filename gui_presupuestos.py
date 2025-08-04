import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import presupuesto_backend # Importamos el módulo con la lógica de backend
import datetime
import os

class PresupuestosAppGUI:
    def __init__(self, master):
        self.master = master
        master.title("Generador de Presupuestos")
        master.geometry("1000x700") # Tamaño de ventana inicial, puedes ajustar

        # --- Variables de estado de la GUI ---
        self.selected_client_id = None
        self.current_budget_items = {} # {codigo_producto: {"id":id, "desc":desc, "cantidad":cant, "precio":precio}}
        self.IVA_RATE = 0.21 # Tasa de IVA, puedes hacerla configurable si quieres

        # --- Mensaje de estado en la parte inferior ---
        self.status_label = tk.Label(master, text="Listo.", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # --- Inicializar la base de datos al inicio de la aplicación ---
        self.update_status("Inicializando base de datos...")
        db_message = presupuesto_backend.inicializar_base_de_datos()
        self.update_status(db_message)
        messagebox.showinfo("Inicio de App", db_message)


        # --- Notebook (Pestañas) ---
        self.notebook = ttk.Notebook(master)
        self.notebook.pack(pady=10, expand=True, fill="both")

        # --- Pestaña de Presupuestos ---
        self.presupuestos_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.presupuestos_frame, text="Presupuestos")
        self.create_presupuestos_tab(self.presupuestos_frame)

        # --- Pestaña de Productos (Inventario) ---
        self.productos_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.productos_frame, text="Productos")
        self.create_productos_tab(self.productos_frame)
        
        # --- Pestaña de Notas de Pedido ---
        self.pedidos_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.pedidos_frame, text="Notas de Pedido")
        self.create_pedidos_tab(self.pedidos_frame)

        # --- Pestaña de Comprobantes ---
        self.comprobantes_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.comprobantes_frame, text="Comprobantes")
        self.create_comprobantes_tab(self.comprobantes_frame)

        # --- Sincronizar todo al inicio (opcional, puede ser solo manual) ---
        self.sync_all_modules_to_sheets()

    def update_status(self, message, is_error=False):
        """Actualiza el mensaje de estado en la GUI."""
        self.status_label.config(text=message, fg="red" if is_error else "black")
        print(f"GUI Status: {message}") # Para ver en la consola de depuración


    # =====================================================================
    # === PESTAÑA DE PRESUPUESTOS ===
    # =====================================================================
    def create_presupuestos_tab(self, parent_frame):
        # Controles para Datos del Presupuesto
        tk.Label(parent_frame, text="Nro. Presupuesto:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.nro_presupuesto_entry = tk.Entry(parent_frame, state="readonly") # Se llenará automáticamente
        self.nro_presupuesto_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        tk.Label(parent_frame, text="Buscar Cliente (Doc/Razón Social):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.search_client_entry = tk.Entry(parent_frame)
        self.search_client_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        tk.Button(parent_frame, text="Buscar Cliente", command=self.search_client).grid(row=1, column=2, padx=5, pady=5)
        tk.Button(parent_frame, text="Nuevo Cliente", command=self.create_new_client).grid(row=1, column=3, padx=5, pady=5)

        tk.Label(parent_frame, text="Cliente Seleccionado:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.selected_client_label = tk.Label(parent_frame, text="Ninguno", fg="blue")
        self.selected_client_label.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky="w")

        tk.Label(parent_frame, text="Fecha:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.fecha_presupuesto_label = tk.Label(parent_frame, text=datetime.date.today().strftime("%d/%m/%Y"))
        self.fecha_presupuesto_label.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        # --- Controles para Agregar Ítem al Presupuesto ---
        ttk.Label(parent_frame, text="Agregar Ítem:", font=("Arial", 10, "bold")).grid(row=4, column=0, columnspan=4, pady=10, sticky="w")

        tk.Label(parent_frame, text="Producto (Nombre/SKU):").grid(row=5, column=0, padx=5, pady=2, sticky="w")
        self.product_search_entry = tk.Entry(parent_frame)
        self.product_search_entry.grid(row=5, column=1, padx=5, pady=2, sticky="ew")
        tk.Button(parent_frame, text="Buscar", command=self.search_product_for_budget).grid(row=5, column=2, padx=5, pady=2)
        
        tk.Label(parent_frame, text="Producto Seleccionado:").grid(row=6, column=0, padx=5, pady=2, sticky="w")
        self.selected_product_label = tk.Label(parent_frame, text="Ninguno", fg="blue")
        self.selected_product_label.grid(row=6, column=1, columnspan=2, padx=5, pady=2, sticky="w")
        self.selected_product_data = None # Para guardar el dict del producto seleccionado

        tk.Label(parent_frame, text="Cantidad:").grid(row=7, column=0, padx=5, pady=2, sticky="w")
        self.cantidad_entry = tk.Entry(parent_frame)
        self.cantidad_entry.grid(row=7, column=1, padx=5, pady=2, sticky="ew")

        tk.Label(parent_frame, text="P. Unitario (sin IVA) USD:").grid(row=8, column=0, padx=5, pady=2, sticky="w")
        self.precio_unitario_entry = tk.Entry(parent_frame)
        self.precio_unitario_entry.grid(row=8, column=1, padx=5, pady=2, sticky="ew")
        
        tk.Button(parent_frame, text="Agregar Ítem", command=self.add_item_to_budget).grid(row=8, column=2, padx=5, pady=5)

        # --- Tabla de Ítems del Presupuesto ---
        tk.Label(parent_frame, text="Ítems del Presupuesto:", font=("Arial", 10, "bold")).grid(row=9, column=0, columnspan=4, pady=10, sticky="w")
        
        self.budget_items_tree = ttk.Treeview(parent_frame, columns=("ID_Prod", "Producto", "Cantidad", "P. Unit.", "Subtotal"), show="headings")
        self.budget_items_tree.heading("ID_Prod", text="ID_Prod")
        self.budget_items_tree.heading("Producto", text="Producto")
        self.budget_items_tree.heading("Cantidad", text="Cantidad")
        self.budget_items_tree.heading("P. Unit.", text="P. Unit. (s/IVA)")
        self.budget_items_tree.heading("Subtotal", text="Subtotal (s/IVA)")

        self.budget_items_tree.column("ID_Prod", width=50, anchor="center")
        self.budget_items_tree.column("Producto", width=200)
        self.budget_items_tree.column("Cantidad", width=80, anchor="center")
        self.budget_items_tree.column("P. Unit.", width=100, anchor="e")
        self.budget_items_tree.column("Subtotal", width=100, anchor="e")
        
        self.budget_items_tree.grid(row=10, column=0, columnspan=4, padx=5, pady=5, sticky="nsew")
        
        parent_frame.grid_rowconfigure(10, weight=1) # Permite que la tabla se expanda
        parent_frame.grid_columnconfigure(1, weight=1) # Permite que el campo de búsqueda se expanda

        # --- Botones de acciones del presupuesto ---
        tk.Button(parent_frame, text="Eliminar Ítem Seleccionado", command=self.remove_item_from_budget).grid(row=11, column=0, padx=5, pady=5, sticky="w")
        tk.Button(parent_frame, text="Nuevo Presupuesto", command=self.clear_budget_form).grid(row=11, column=2, padx=5, pady=5)
        tk.Button(parent_frame, text="Guardar Presupuesto", command=self.save_budget).grid(row=11, column=3, padx=5, pady=5)

        # --- Totales del Presupuesto ---
        # Puedes usar Labels para mostrar los totales, actualizándolos cada vez que se agrega/elimina un ítem.
        # Los cálculos de IVA, Total General, etc. se harán en funciones auxiliares.
        self.total_sin_iva_label = tk.Label(parent_frame, text="Total (s/IVA): 0.00 USD", font=("Arial", 10, "bold"))
        self.total_sin_iva_label.grid(row=12, column=2, columnspan=2, sticky="e", padx=5, pady=2)
        self.iva_label = tk.Label(parent_frame, text="IVA (21%): 0.00 USD")
        self.iva_label.grid(row=13, column=2, columnspan=2, sticky="e", padx=5, pady=2)
        self.total_con_iva_label = tk.Label(parent_frame, text="Total (c/IVA): 0.00 USD", font=("Arial", 10, "bold"))
        self.total_con_iva_label.grid(row=14, column=2, columnspan=2, sticky="e", padx=5, pady=2)


        # --- Tabla de Historial de Presupuestos ---
        tk.Label(parent_frame, text="Historial de Presupuestos:", font=("Arial", 10, "bold")).grid(row=15, column=0, columnspan=4, pady=10, sticky="w")
        
        self.list_all_budgets_tree = ttk.Treeview(parent_frame, columns=("ID", "Cliente", "Fecha", "Estado", "Total"), show="headings")
        self.list_all_budgets_tree.heading("ID", text="ID")
        self.list_all_budgets_tree.heading("Cliente", text="Cliente")
        self.list_all_budgets_tree.heading("Fecha", text="Fecha")
        self.list_all_budgets_tree.heading("Estado", text="Estado")
        self.list_all_budgets_tree.heading("Total", text="Total")

        self.list_all_budgets_tree.column("ID", width=50, anchor="center")
        self.list_all_budgets_tree.column("Cliente", width=150)
        self.list_all_budgets_tree.column("Fecha", width=100)
        self.list_all_budgets_tree.column("Estado", width=100, anchor="center")
        self.list_all_budgets_tree.column("Total", width=100, anchor="e")

        self.list_all_budgets_tree.grid(row=16, column=0, columnspan=4, padx=5, pady=5, sticky="nsew")
        parent_frame.grid_rowconfigure(16, weight=1) # Permite que la tabla de historial se expanda
        
        # Botones para el historial de presupuestos
        tk.Button(parent_frame, text="Actualizar Estado Presupuesto", command=self.update_budget_status_gui).grid(row=17, column=0, padx=5, pady=5, sticky="w")
        tk.Button(parent_frame, text="Ver Detalles Presupuesto", command=self.view_budget_details_gui).grid(row=17, column=1, padx=5, pady=5, sticky="w")

        # Cargar presupuestos existentes al iniciar la pestaña
        self.load_all_budgets() 


    def search_client(self):
        """Busca un cliente y lo selecciona en la GUI."""
        client_name = self.search_client_entry.get().strip()
        if not client_name:
            self.update_status("Ingrese un nombre de cliente para buscar.", True)
            return

        client_id, message, is_error = presupuesto_backend.obtener_o_crear_cliente(client_name)

        if is_error:
            if "no existe" in message:
                response = messagebox.askyesno("Cliente No Existe", f"{message}\n¿Desea registrarlo?")
                if response:
                    self.create_new_client(client_name=client_name)
                else:
                    self.update_status("Operación cancelada. Cliente no seleccionado.", True)
                    self.selected_client_id = None
                    self.selected_client_label.config(text="Ninguno", fg="red")
            else:
                self.update_status(f"Error al buscar cliente: {message}", True)
                self.selected_client_id = None
                self.selected_client_label.config(text="Ninguno", fg="red")
        else:
            self.selected_client_id = client_id
            client_data = presupuesto_backend.obtener_cliente_por_id(client_id)
            self.selected_client_label.config(text=f"{client_data['nombre']} (CUIT: {client_data['cuit']})", fg="blue")
            self.update_status(message, False)
    
    def create_new_client(self, client_name=""):
        """Abre un diálogo para crear un nuevo cliente."""
        if not client_name:
            client_name = simpledialog.askstring("Nuevo Cliente", "Ingrese el nombre del nuevo cliente:")
            if not client_name: return

        cuit = simpledialog.askstring("Nuevo Cliente", f"Ingrese el CUIT para {client_name}:")
        razon_social = simpledialog.askstring("Nuevo Cliente", f"Ingrese la Razón Social para {client_name}:")

        if cuit and razon_social:
            client_id, message, is_error = presupuesto_backend.obtener_o_crear_cliente(client_name, cuit, razon_social)
            if is_error:
                messagebox.showerror("Error al crear cliente", message)
                self.update_status(f"Error: {message}", True)
            else:
                self.selected_client_id = client_id
                client_data = presupuesto_backend.obtener_cliente_por_id(client_id)
                self.selected_client_label.config(text=f"{client_data['nombre']} (CUIT: {client_data['cuit']})", fg="blue")
                messagebox.showinfo("Cliente Creado", message)
                self.update_status(message, False)
                self.sync_module_to_sheets('comprobantes')
        else:
            messagebox.showwarning("Advertencia", "CUIT y Razón Social son obligatorios para crear un cliente.")
            self.update_status("Creación de cliente cancelada.", True)


    def search_product_for_budget(self):
        """Busca un producto para agregarlo al presupuesto."""
        product_code = self.product_search_entry.get().strip().upper()
        if not product_code:
            self.update_status("Ingrese un código de producto para buscar.", True)
            return

        product_data = presupuesto_backend.obtener_producto_por_codigo(product_code)

        if product_data:
            self.selected_product_data = product_data
            self.selected_product_label.config(text=f"{product_data['descripcion']} (Stock Disp: {product_data['stock_disponible'] - product_data['stock_reservado']})", fg="blue")
            self.precio_unitario_entry.delete(0, tk.END)
            self.precio_unitario_entry.insert(0, f"{product_data['precio_1']:.2f}") # Sugerir precio_1 por defecto
            self.update_status(f"Producto '{product_data['descripcion']}' encontrado.", False)
        else:
            self.update_status(f"Producto con código '{product_code}' no encontrado.", True)
            self.selected_product_data = None
            self.selected_product_label.config(text="Ninguno", fg="red")
            self.precio_unitario_entry.delete(0, tk.END)

    def add_item_to_budget(self):
        """Agrega el producto seleccionado a la tabla de ítems del presupuesto."""
        if not self.selected_product_data:
            messagebox.showwarning("Advertencia", "Primero debe seleccionar un producto.")
            return
        
        try:
            cantidad = int(self.cantidad_entry.get())
            if cantidad <= 0:
                messagebox.showerror("Error", "La cantidad debe ser mayor a 0.")
                return
        except ValueError:
            messagebox.showerror("Error", "Cantidad inválida. Ingrese un número.")
            return

        try:
            precio_unitario = float(self.precio_unitario_entry.get().replace(',', '.'))
            if precio_unitario <= 0:
                messagebox.showerror("Error", "El precio unitario debe ser mayor a 0.")
                return
        except ValueError:
            messagebox.showerror("Error", "Precio unitario inválido. Ingrese un número.")
            return

        # Alerta de stock (solo visual para el vendedor)
        stock_no_reservado = self.selected_product_data['stock_disponible'] - self.selected_product_data['stock_reservado']
        if cantidad > stock_no_reservado:
            messagebox.showwarning("Alerta de Stock", f"La cantidad solicitada ({cantidad}) excede el stock disponible no reservado ({stock_no_reservado}).")
        
        # Agregar el ítem a la tabla del presupuesto
        product_id = self.selected_product_data['id']
        product_desc = self.selected_product_data['descripcion']
        subtotal = cantidad * precio_unitario

        # Si el ítem ya está en la lista, sumar la cantidad
        if product_id in self.current_budget_items:
            old_item = self.current_budget_items[product_id]
            new_cantidad = old_item["cantidad"] + cantidad
            new_subtotal = new_cantidad * old_item["precio"]
            self.budget_items_tree.item(old_item["tree_item_id"], values=(product_id, product_desc, new_cantidad, old_item["precio"], new_subtotal))
            self.current_budget_items[product_id]["cantidad"] = new_cantidad
            self.current_budget_items[product_id]["subtotal"] = new_subtotal
        else:
            tree_item_id = self.budget_items_tree.insert("", tk.END, values=(product_id, product_desc, cantidad, precio_unitario, subtotal))
            self.current_budget_items[product_id] = {
                "id": product_id,
                "desc": product_desc,
                "cantidad": cantidad,
                "precio": precio_unitario,
                "subtotal": subtotal,
                "tree_item_id": tree_item_id # Guardar el ID del item en el Treeview
            }
        
        self.update_status(f"Ítem '{product_desc}' agregado al presupuesto.")
        self.cantidad_entry.delete(0, tk.END)
        # Limpiar campos de producto seleccionado
        self.selected_product_data = None
        self.product_search_entry.delete(0, tk.END)
        self.selected_product_label.config(text="Ninguno", fg="blue")
        self.precio_unitario_entry.delete(0, tk.END)
        
        self.calculate_budget_totals() # Recalcular totales

    def remove_item_from_budget(self):
        """Elimina el ítem seleccionado de la tabla de ítems del presupuesto."""
        selected_item = self.budget_items_tree.focus()
        if not selected_item:
            messagebox.showwarning("Advertencia", "Seleccione un ítem para eliminar.")
            return

        item_values = self.budget_items_tree.item(selected_item, 'values')
        product_id = item_values[0] # El ID del producto está en la primera columna

        del self.current_budget_items[product_id] # Eliminar del diccionario de control
        self.budget_items_tree.delete(selected_item) # Eliminar del Treeview
        self.update_status(f"Ítem '{item_values[1]}' eliminado del presupuesto.")
        self.calculate_budget_totals() # Recalcular totales


    def calculate_budget_totals(self):
        """Calcula y muestra los totales del presupuesto."""
        total_sin_iva = sum(item["subtotal"] for item in self.current_budget_items.values())
        iva = total_sin_iva * self.IVA_RATE
        total_con_iva = total_sin_iva + iva
        
        self.total_sin_iva_label.config(text=f"Total (s/IVA): {total_sin_iva:.2f} USD")
        self.iva_label.config(text=f"IVA ({self.IVA_RATE*100:.0f}%): {iva:.2f} USD")
        self.total_con_iva_label.config(text=f"Total (c/IVA): {total_con_iva:.2f} USD")


    def clear_budget_form(self):
        """Limpia el formulario del presupuesto para crear uno nuevo."""
        self.nro_presupuesto_entry.config(state="normal")
        self.nro_presupuesto_entry.delete(0, tk.END)
        self.nro_presupuesto_entry.config(state="readonly")
        
        self.search_client_entry.delete(0, tk.END)
        self.selected_client_label.config(text="Ninguno", fg="blue")
        self.selected_client_id = None

        self.product_search_entry.delete(0, tk.END)
        self.selected_product_label.config(text="Ninguno", fg="blue")
        self.cantidad_entry.delete(0, tk.END)
        self.precio_unitario_entry.delete(0, tk.END)
        self.selected_product_data = None

        for item in self.budget_items_tree.get_children():
            self.budget_items_tree.delete(item)
        self.current_budget_items = {} # Limpiar ítems del presupuesto
        
        self.calculate_budget_totals() # Resetear totales
        self.update_status("Formulario de presupuesto limpiado para uno nuevo.")
        self.load_all_budgets() # Recargar la tabla de presupuestos existentes


    def save_budget(self):
        """Guarda el presupuesto actual en la base de datos."""
        if not self.selected_client_id:
            messagebox.showwarning("Advertencia", "Debe seleccionar un cliente para guardar el presupuesto.")
            return
        if not self.current_budget_items:
            messagebox.showwarning("Advertencia", "Agregue ítems al presupuesto antes de guardar.")
            return
        
        # Convertir el diccionario de ítems a la lista de tuplas que espera el backend
        detalle_presupuesto_list = [
            (item["id"], item["cantidad"], item["precio"]) 
            for item in self.current_budget_items.values()
        ]

        budget_id, message, is_error = presupuesto_backend.crear_presupuesto(
            self.selected_client_id, detalle_presupuesto_list
        )

        if is_error:
            messagebox.showerror("Error al guardar presupuesto", message)
            self.update_status(f"Error al guardar presupuesto: {message}", True)
        else:
            self.update_status(f"✅ {message}", False)
            messagebox.showinfo("Presupuesto Guardado", message)
            self.sync_module_to_sheets('presupuestos') # Sincronizar presupuestos a Sheets
            self.clear_budget_form() # Limpiar para un nuevo presupuesto
            self.load_all_budgets() # Recargar la tabla de presupuestos existentes

    def load_all_budgets(self):
        """Carga y muestra todos los presupuestos existentes."""
        self.list_all_budgets_tree.delete(*self.list_all_budgets_tree.get_children()) # Limpiar tabla existente
        
        budgets = presupuesto_backend.obtener_todos_los_presupuestos()
        if not budgets:
            self.update_status("No hay presupuestos registrados.", False)
            return

        for budget in budgets:
            state = budget[3]
            if state == 'aprobado': color_tag = 'aprobado_tag'
            elif state == 'facturado': color_tag = 'facturado_tag'
            elif state == 'borrador': color_tag = 'borrador_tag'
            elif state == 'rechazado': color_tag = 'rechazado_tag'
            else: color_tag = 'default_tag' # Para cualquier otro estado desconocido

            self.list_all_budgets_tree.insert("", tk.END, values=(budget[0], budget[1], budget[2], state, f"{budget[4]:.2f}"), tags=(color_tag,))
        
        # Configurar colores para los tags del Treeview
        self.list_all_budgets_tree.tag_configure('aprobado_tag', background='lightgreen')
        self.list_all_budgets_tree.tag_configure('facturado_tag', background='lightblue')
        self.list_all_budgets_tree.tag_configure('borrador_tag', background='lightgrey')
        self.list_all_budgets_tree.tag_configure('rechazado_tag', background='salmon')
        self.list_all_budgets_tree.tag_configure('default_tag', background='white') # Por defecto
        
        self.update_status(f"Cargados {len(budgets)} presupuestos.")
    
    def update_budget_status_gui(self):
        selected_item = self.list_all_budgets_tree.focus()
        if not selected_item:
            messagebox.showwarning("Advertencia", "Seleccione un presupuesto para actualizar su estado.")
            return
        
        budget_id = self.list_all_budgets_tree.item(selected_item, 'values')[0]
        current_status = self.list_all_budgets_tree.item(selected_item, 'values')[3]

        new_status = simpledialog.askstring("Actualizar Estado Presupuesto", f"Estado actual: {current_status}\nIngrese el nuevo estado (borrador, aprobado, facturado, rechazado):").strip().lower()
        if not new_status: return

        create_np = False
        if new_status == 'facturado' and current_status != 'facturado':
            response = messagebox.askyesno("Facturar Presupuesto", "¿Desea crear una Nota de Pedido a partir de este presupuesto?")
            if response:
                create_np = True

        success, message = presupuesto_backend.actualizar_estado_presupuesto(budget_id, new_status, create_np)
        
        if success:
            messagebox.showinfo("Estado Actualizado", message)
            self.update_status(message)
            self.load_all_budgets() # Recargar la tabla de presupuestos
            self.sync_module_to_sheets('presupuestos')
            if create_np: # Si se creó una NP, sincronizar también pedidos y productos
                self.sync_module_to_sheets('pedidos')
                self.sync_module_to_sheets('productos')
        else:
            messagebox.showerror("Error", message)
            self.update_status(f"Error: {message}", True)

    def view_budget_details_gui(self):
        selected_item = self.list_all_budgets_tree.focus()
        if not selected_item:
            messagebox.showwarning("Advertencia", "Seleccione un presupuesto para ver detalles.")
            return
        
        budget_id = self.list_all_budgets_tree.item(selected_item, 'values')[0]
        
        details, error_message = presupuesto_backend.obtener_detalle_presupuesto(budget_id)
        
        if error_message:
            messagebox.showerror("Error", error_message)
            return

        detail_window = tk.Toplevel(self.master)
        detail_window.title(f"Detalles Presupuesto #{budget_id}")
        
        # Mostrar información general del presupuesto
        tk.Label(detail_window, text=f"Cliente: {details['presupuesto'][1]}").pack(pady=2)
        tk.Label(detail_window, text=f"Fecha: {details['presupuesto'][2]}").pack(pady=2)
        tk.Label(detail_window, text=f"Estado: {details['presupuesto'][3]}").pack(pady=2)
        
        tk.Label(detail_window, text="Ítems:", font=("Arial", 10, "bold")).pack(pady=5)
        
        # Tabla de ítems del detalle
        detail_tree = ttk.Treeview(detail_window, columns=("Código", "Descripción", "Cantidad", "P. Unit.", "Subtotal"), show="headings")
        detail_tree.heading("Código", text="Código")
        detail_tree.heading("Descripción", text="Descripción")
        detail_tree.heading("Cantidad", text="Cantidad")
        detail_tree.heading("P. Unit.", text="P. Unit. (s/IVA)")
        detail_tree.heading("Subtotal", text="Subtotal (s/IVA)")
        
        detail_tree.column("Código", width=100)
        detail_tree.column("Descripción", width=200)
        detail_tree.column("Cantidad", width=80, anchor="center")
        detail_tree.column("P. Unit.", width=100, anchor="e")
        detail_tree.column("Subtotal", width=100, anchor="e")
        
        total_items = 0
        for item in details['detalles']:
            subtotal = item[2] * item[3]
            total_items += subtotal
            detail_tree.insert("", tk.END, values=(item[0], item[1], item[2], f"{item[3]:.2f}", f"{subtotal:.2f}"))
        
        detail_tree.pack(expand=True, fill="both", padx=10, pady=5)
        
        tk.Label(detail_window, text=f"Total Presupuesto: {total_items:.2f} USD", font=("Arial", 10, "bold")).pack(pady=5)


    # =====================================================================
    # === PESTAÑA DE PRODUCTOS (INVENTARIO) ===
    # =====================================================================
    def create_productos_tab(self, parent_frame):
        # Controles para agregar/modificar productos
        tk.Label(parent_frame, text="Código:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.prod_code_entry = tk.Entry(parent_frame)
        self.prod_code_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        tk.Label(parent_frame, text="Descripción:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.prod_desc_entry = tk.Entry(parent_frame)
        self.prod_desc_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        tk.Label(parent_frame, text="Stock Inicial/Cambio:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.prod_stock_entry = tk.Entry(parent_frame)
        self.prod_stock_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        tk.Button(parent_frame, text="Agregar Producto", command=self.add_product_gui).grid(row=3, column=0, padx=5, pady=5)
        tk.Button(parent_frame, text="Modificar Stock", command=self.modify_stock_gui).grid(row=3, column=1, padx=5, pady=5)
        tk.Button(parent_frame, text="Actualizar Estado", command=self.change_product_status_gui).grid(row=3, column=2, padx=5, pady=5)
        tk.Button(parent_frame, text="Cargar Productos", command=self.load_products_to_treeview).grid(row=3, column=3, padx=5, pady=5) # Botón para recargar tabla

        # Tabla de Productos
        self.products_tree = ttk.Treeview(parent_frame, columns=("ID", "Codigo", "Descripcion", "Disp", "Res", "Estado", "Precio 1"), show="headings")
        self.products_tree.heading("ID", text="ID")
        self.products_tree.heading("Codigo", text="Código")
        self.products_tree.heading("Descripcion", text="Descripción")
        self.products_tree.heading("Disp", text="Disp.")
        self.products_tree.heading("Res", text="Res.")
        self.products_tree.heading("Estado", text="Estado")
        self.products_tree.heading("Precio 1", text="P. (1)")
        
        self.products_tree.column("ID", width=40, anchor="center")
        self.products_tree.column("Codigo", width=100)
        self.products_tree.column("Descripcion", width=200)
        self.products_tree.column("Disp", width=60, anchor="center")
        self.products_tree.column("Res", width=60, anchor="center")
        self.products_tree.column("Estado", width=100)
        self.products_tree.column("Precio 1", width=80, anchor="e")

        self.products_tree.grid(row=4, column=0, columnspan=4, padx=5, pady=5, sticky="nsew")
        parent_frame.grid_rowconfigure(4, weight=1)
        parent_frame.grid_columnconfigure(1, weight=1)

        self.load_products_to_treeview() # Cargar productos al iniciar la pestaña

    def add_product_gui(self):
        codigo = self.prod_code_entry.get().strip()
        descripcion = self.prod_desc_entry.get().strip()
        stock_str = self.prod_stock_entry.get().strip()

        if not codigo or not descripcion or not stock_str:
            messagebox.showwarning("Advertencia", "Todos los campos son obligatorios.")
            return

        try:
            stock = int(stock_str)
            if stock < 0:
                messagebox.showerror("Error", "El stock no puede ser negativo.")
                return
        except ValueError:
            messagebox.showerror("Error", "Stock inválido. Ingrese un número entero.")
            return

        success, message = presupuesto_backend.agregar_producto(codigo, descripcion, stock)
        if success:
            messagebox.showinfo("Éxito", message)
            self.update_status(message)
            self.load_products_to_treeview() # Recargar la tabla
            self.sync_module_to_sheets('productos')
        else:
            messagebox.showerror("Error", message)
            self.update_status(f"Error: {message}", True)

    def modify_stock_gui(self):
        codigo = self.prod_code_entry.get().strip()
        stock_change_str = self.prod_stock_entry.get().strip()

        if not codigo or not stock_change_str:
            messagebox.showwarning("Advertencia", "Ingrese código de producto y la cantidad de cambio de stock.")
            return
        
        try:
            stock_change = int(stock_change_str)
        except ValueError:
            messagebox.showerror("Error", "Cantidad de cambio de stock inválida. Ingrese un número entero.")
            return

        success, message = presupuesto_backend.modificar_stock_producto(codigo, stock_change)
        if success:
            messagebox.showinfo("Éxito", message)
            self.update_status(message)
            self.load_products_to_treeview() # Recargar la tabla
            self.sync_module_to_sheets('productos')
        else:
            messagebox.showerror("Error", message)
            self.update_status(f"Error: {message}", True)

    def change_product_status_gui(self):
        codigo = self.prod_code_entry.get().strip()
        if not codigo:
            messagebox.showwarning("Advertencia", "Ingrese el código del producto a actualizar.")
            return
        
        # Aquí podrías usar un Combobox para seleccionar el estado, para este ejemplo simpledialog
        new_status = simpledialog.askstring("Cambiar Estado", "Ingrese el nuevo estado (disponible, discontinuado, en_transito, pedida, sin_stock):").strip().lower()
        if not new_status: return

        success, message = presupuesto_backend.cambiar_estado_producto_manual(codigo, new_status)
        if success:
            messagebox.showinfo("Éxito", message)
            self.update_status(message)
            self.load_products_to_treeview() # Recargar la tabla
            self.sync_module_to_sheets('productos')
        else:
            messagebox.showerror("Error", message)
            self.update_status(f"Error: {message}", True)

    def load_products_to_treeview(self):
        """Carga los productos de la DB en el Treeview de la pestaña de productos."""
        for item in self.products_tree.get_children():
            self.products_tree.delete(item)
        
        products = presupuesto_backend.obtener_todos_los_productos()
        if products:
            for p in products:
                # p = (id, codigo, descripcion, stock_disponible, stock_reservado, estado_producto, precio_1, precio_5, precio_10)
                self.products_tree.insert('', tk.END, values=(p[0], p[1], p[2], p[3], p[4], p[5], f"{p[6]:.2f}")) # ID, Código, Desc, Disp, Res, Estado, Precio_1
        self.update_status(f"Cargados {len(products)} productos en la tabla.")


    # =====================================================================
    # === PESTAÑA DE NOTAS DE PEDIDO ===
    # =====================================================================
    def create_pedidos_tab(self, parent_frame):
        # Aquí irían los controles para crear y ver notas de pedido
        tk.Label(parent_frame, text="Gestión de Notas de Pedido", font=("Arial", 12, "bold")).pack(pady=10)
        
        tk.Button(parent_frame, text="Crear Nueva Nota de Pedido", command=self.create_new_order_gui).pack(pady=5)
        tk.Button(parent_frame, text="Ver Todas las Notas de Pedido", command=lambda: self.load_orders_to_treeview(False)).pack(pady=5)
        tk.Button(parent_frame, text="Ver Notas para Expedición", command=lambda: self.load_orders_to_treeview(True)).pack(pady=5)
        tk.Button(parent_frame, text="Actualizar Estado de Nota de Pedido", command=self.update_order_status_gui).pack(pady=5)

        # Tabla de Notas de Pedido
        self.orders_tree = ttk.Treeview(parent_frame, columns=("ID", "Cliente", "Fecha", "Entrega", "Estado", "Total"), show="headings")
        self.orders_tree.heading("ID", text="ID")
        self.orders_tree.heading("Cliente", text="Cliente")
        self.orders_tree.heading("Fecha", text="Fecha")
        self.orders_tree.heading("Entrega", text="Entrega")
        self.orders_tree.heading("Estado", text="Estado")
        self.orders_tree.heading("Total", text="Total")

        self.orders_tree.column("ID", width=50, anchor="center")
        self.orders_tree.column("Cliente", width=150)
        self.orders_tree.column("Fecha", width=100)
        self.orders_tree.column("Entrega", width=120)
        self.orders_tree.column("Estado", width=100, anchor="center")
        self.orders_tree.column("Total", width=100, anchor="e")

        self.orders_tree.pack(pady=10, expand=True, fill="both")
        
        # Configurar colores para los tags del Treeview de pedidos
        self.orders_tree.tag_configure('aprobado_tag', background='lightgreen')
        self.orders_tree.tag_configure('pendiente_tag', background='yellow')
        self.orders_tree.tag_configure('entregada_tag', background='salmon')
        self.orders_tree.tag_configure('cancelado_tag', background='lightgrey')
        self.orders_tree.tag_configure('default_tag', background='white')

        self.load_orders_to_treeview(False) # Cargar todas al inicio

    def create_new_order_gui(self):
        # Simulación: abrir una ventana simple para crear pedido.
        # En tu app real, esto sería una ventana de formulario completa.
        if not self.selected_client_id:
            messagebox.showwarning("Advertencia", "Primero debe seleccionar un cliente en la pestaña de presupuestos/clientes.")
            return

        dialog = simpledialog.askstring("Tipo de Entrega", "Es 'Retiro por mostrador' o 'Envío'? (mostrador/envio):")
        if dialog is None: return

        tipo_entrega = dialog.lower()
        direccion = None
        telefono = None

        if tipo_entrega == 'envio':
            direccion = simpledialog.askstring("Envío", "Ingrese dirección de envío:")
            telefono = simpledialog.askstring("Envío", "Ingrese teléfono de contacto:")
            if not direccion or not telefono:
                messagebox.showwarning("Advertencia", "Dirección y teléfono son obligatorios para envío.")
                return
        elif tipo_entrega != 'mostrador':
            messagebox.showerror("Error", "Tipo de entrega inválido.")
            return

        # Para simplificar, agregar un solo producto de ejemplo.
        # En la app real, aquí se recopilarían los items de una tabla de la GUI.
        product_code = simpledialog.askstring("Agregar Producto a Pedido", "Ingrese código del producto (ej: LAPTOP001):")
        if not product_code: return

        product_data = presupuesto_backend.obtener_producto_por_codigo(product_code)
        if not product_data:
            messagebox.showerror("Error", "Producto no encontrado.")
            return

        try:
            cantidad = simpledialog.askinteger("Agregar Producto a Pedido", f"Cantidad para {product_data['descripcion']}:")
            precio_unitario = simpledialog.askfloat("Agregar Producto a Pedido", f"Precio unitario para {product_data['descripcion']} (sugerido {product_data['precio_1']:.2f}):")
            if cantidad is None or precio_unitario is None or cantidad <= 0 or precio_unitario <= 0: raise ValueError
        except (ValueError, TypeError):
            messagebox.showerror("Error", "Cantidad o precio inválido o no ingresado.")
            return
        
        detalle_pedido_list = [(product_data['id'], cantidad, precio_unitario)]

        order_id, message, is_error = presupuesto_backend.crear_nota_pedido(
            self.selected_client_id, detalle_pedido_list, tipo_entrega, direccion, telefono
        )

        if is_error:
            messagebox.showerror("Error al crear pedido", message)
            self.update_status(f"Error: {message}", True)
        else:
            messagebox.showinfo("Pedido Creado", message)
            self.update_status(f"✅ {message}", False)
            self.load_orders_to_treeview(False) # Recargar lista de pedidos
            self.sync_module_to_sheets('pedidos') # Sincronizar pedidos
            self.sync_module_to_sheets('productos') # Sincronizar productos (por si afecta stock_reservado)

    def load_orders_to_treeview(self, filter_expedition=False):
        """Carga las notas de pedido en el Treeview."""
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)

        orders = presupuesto_backend.obtener_notas_pedido(filter_expedition)
        if orders:
            for order in orders:
                state = order[6]
                if state == 'aprobada': color_tag = 'aprobado_tag'
                elif state == 'pendiente': color_tag = 'pendiente_tag'
                elif state == 'entregada': color_tag = 'entregada_tag'
                elif state == 'cancelada': color_tag = 'cancelado_tag'
                else: color_tag = 'default_tag' # para cualquier otro estado desconocido

                self.orders_tree.insert("", tk.END, values=(order[0], order[1], order[2], order[3], state, f"{order[7]:.2f}"), tags=(color_tag,))
            
        self.update_status(f"Cargadas {len(orders)} notas de pedido.")

    def update_order_status_gui(self):
        selected_item = self.orders_tree.focus()
        if not selected_item:
            messagebox.showwarning("Advertencia", "Seleccione una nota de pedido para actualizar.")
            return
        
        order_id = self.orders_tree.item(selected_item, 'values')[0]
        current_status = self.orders_tree.item(selected_item, 'values')[4] # El estado está en la 5ta columna

        new_status = simpledialog.askstring("Actualizar Estado Nota de Pedido", f"Estado actual: {current_status}\nIngrese el nuevo estado (pendiente, aprobada, entregada, cancelada):").strip().lower()
        if new_status is None: return # Si el usuario cancela el diálogo

        success, message = presupuesto_backend.actualizar_estado_nota_pedido(order_id, new_status)
        
        if success:
            messagebox.showinfo("Estado Actualizado", message)
            self.update_status(message)
            self.load_orders_to_treeview(False) # Recargar la tabla
            self.sync_module_to_sheets('pedidos')
            self.sync_module_to_sheets('productos')
        else:
            messagebox.showerror("Error", message)
            self.update_status(f"Error: {message}", True)


    # =====================================================================
    # === PESTAÑA DE COMPROBANTES ===
    # =====================================================================
    def create_comprobantes_tab(self, parent_frame):
        tk.Label(parent_frame, text="Gestión de Comprobantes (OCR)", font=("Arial", 12, "bold")).pack(pady=10)
        
        tk.Label(parent_frame, text="Ruta del Archivo (PDF/IMG):").pack(pady=2)
        self.comprobante_path_entry = tk.Entry(parent_frame, width=50)
        self.comprobante_path_entry.pack(pady=2)
        tk.Button(parent_frame, text="Seleccionar Archivo", command=self.select_comprobante_file).pack(pady=5)
        tk.Button(parent_frame, text="Extraer Datos del Comprobante", command=self.extract_comprobante_data).pack(pady=5) # Separar extracción de guardado

        # Para mostrar datos extraídos y permitir edición
        tk.Label(parent_frame, text="Datos Extraídos (Editar si es necesario):", font=("Arial", 10, "bold")).pack(pady=10)
        tk.Label(parent_frame, text="Nro. Operación:").pack()
        self.nro_operacion_entry = tk.Entry(parent_frame)
        self.nro_operacion_entry.pack()
        tk.Label(parent_frame, text="Fecha (DD/MM/AAAA):").pack()
        self.fecha_comprobante_entry = tk.Entry(parent_frame)
        self.fecha_comprobante_entry.pack()
        tk.Label(parent_frame, text="Importe:").pack()
        self.importe_comprobante_entry = tk.Entry(parent_frame)
        self.importe_comprobante_entry.pack()
        tk.Label(parent_frame, text="Cuenta:").pack()
        self.cuenta_comprobante_entry = tk.Entry(parent_frame)
        self.cuenta_comprobante_entry.pack()
        tk.Button(parent_frame, text="Guardar Comprobante", command=self.save_comprobante_from_gui).pack(pady=5) # Botón para guardar después de extraer/editar

        # Tabla de Comprobantes (opcional, para ver historial)
        self.comprobantes_tree = ttk.Treeview(parent_frame, columns=("ID", "Cliente", "Nro Op", "Fecha", "Importe"), show="headings")
        self.comprobantes_tree.heading("ID", text="ID")
        self.comprobantes_tree.heading("Cliente", text="Cliente")
        self.comprobantes_tree.heading("Nro Op", text="Nro Op")
        self.comprobantes_tree.heading("Fecha", text="Fecha")
        self.comprobantes_tree.heading("Importe", text="Importe")
        self.comprobantes_tree.pack(pady=10, expand=True, fill="both")

        self.load_comprobantes_to_treeview() # Cargar comprobantes existentes

    def select_comprobante_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("PDF files", "*.pdf"), ("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")]
        )
        if file_path:
            self.comprobante_path_entry.delete(0, tk.END)
            self.comprobante_path_entry.insert(0, file_path)
            self.update_status(f"Archivo seleccionado: {file_path}")

    def extract_comprobante_data(self):
        file_path = self.comprobante_path_entry.get().strip()
        if not file_path:
            messagebox.showwarning("Advertencia", "Seleccione un archivo de comprobante.")
            return

        extracted_data, error_message = presupuesto_backend.extraer_datos_comprobante(file_path)

        if error_message:
            messagebox.showerror("Error de Extracción OCR", error_message)
            self.update_status(f"Error OCR: {error_message}", True)
            self.clear_comprobante_entries() # Limpiar para entrada manual
            return
        
        if extracted_data:
            self.nro_operacion_entry.delete(0, tk.END)
            self.nro_operacion_entry.insert(0, extracted_data.get("nro_operacion", ""))
            self.fecha_comprobante_entry.delete(0, tk.END)
            self.fecha_comprobante_entry.insert(0, extracted_data.get("fecha", ""))
            self.importe_comprobante_entry.delete(0, tk.END)
            self.importe_comprobante_entry.insert(0, f"{extracted_data.get('importe', ''):.2f}" if extracted_data.get('importe') is not None else "")
            self.cuenta_comprobante_entry.delete(0, tk.END)
            self.cuenta_comprobante_entry.insert(0, extracted_data.get("cuenta", ""))
            self.update_status("Datos extraídos. Revise y guarde.")
        else:
            messagebox.showwarning("Advertencia", "No se pudieron extraer datos automáticamente. Por favor, ingrese manualmente.")
            self.clear_comprobante_entries() # Limpiar para entrada manual

    def clear_comprobante_entries(self):
        self.nro_operacion_entry.delete(0, tk.END)
        self.fecha_comprobante_entry.delete(0, tk.END)
        self.importe_comprobante_entry.delete(0, tk.END)
        self.cuenta_comprobante_entry.delete(0, tk.END)

    def save_comprobante_from_gui(self):
        if not self.selected_client_id:
            messagebox.showwarning("Advertencia", "Primero debe seleccionar un cliente en la pestaña de presupuestos/clientes.")
            return

        nro_operacion = self.nro_operacion_entry.get().strip()
        fecha = self.fecha_comprobante_entry.get().strip()
        importe_str = self.importe_comprobante_entry.get().strip().replace(',', '.')
        cuenta = self.cuenta_comprobante_entry.get().strip()

        if not nro_operacion or not fecha or not importe_str or not cuenta:
            messagebox.showerror("Error", "Todos los campos del comprobante son obligatorios.")
            return
        
        try:
            importe = float(importe_str)
        except ValueError:
            messagebox.showerror("Error", "Importe inválido. Ingrese un número válido.")
            return

        success, message = presupuesto_backend.guardar_comprobante(
            nro_operacion, fecha, importe, cuenta, self.selected_client_id
        )

        if success:
            messagebox.showinfo("Comprobante Guardado", message)
            self.update_status(message)
            self.load_comprobantes_to_treeview() # Recargar tabla
            self.sync_module_to_sheets('comprobantes')
            self.clear_comprobante_entries() # Limpiar campos
            self.comprobante_path_entry.delete(0, tk.END) # Limpiar ruta de archivo
        else:
            messagebox.showerror("Error al guardar comprobante", message)
            self.update_status(f"Error: {message}", True)

    def load_comprobantes_to_treeview(self):
        for item in self.comprobantes_tree.get_children():
            self.comprobantes_tree.delete(item)

        # Cargar comprobantes (obtener_comprobantes no existe en backend, la hacemos aquí para demo)
        conn = sqlite3.connect('presupuestos.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT comp.id, c.nombre, comp.nro_operacion, comp.fecha, comp.importe
            FROM comprobantes comp JOIN clientes c ON comp.cliente_id = c.id
            ORDER BY comp.fecha DESC
        """)
        comprobantes = cursor.fetchall()
        conn.close()

        if comprobantes:
            for comp in comprobantes:
                self.comprobantes_tree.insert("", tk.END, values=comp)
        self.update_status(f"Cargados {len(comprobantes)} comprobantes.")


    # =====================================================================
    # === FUNCIONES DE SINCRONIZACIÓN GENERAL ===
    # =====================================================================
    def sync_module_to_sheets(self, module_name):
        """Función genérica para sincronizar un módulo y mostrar el estado."""
        success, message = presupuesto_backend.sincronizar_a_google_sheets(modulo=module_name)
        if success:
            self.update_status(f"Sincronización de '{module_name}' exitosa: {message}")
        else:
            self.update_status(f"Error al sincronizar '{module_name}': {message}", True)
            messagebox.showerror(f"Error Sincronización {module_name}", message)

    def sync_all_modules_to_sheets(self):
        """Sincroniza todos los módulos con Google Sheets."""
        self.update_status("Sincronizando todos los módulos...")
        self.sync_module_to_sheets('productos')
        self.sync_module_to_sheets('pedidos')
        self.sync_module_to_sheets('presupuestos')
        self.sync_module_to_sheets('comprobantes')
        self.update_status("Sincronización completa de todos los módulos.")

# --- Punto de entrada de la aplicación ---
if __name__ == "__main__":
    root = tk.Tk()
    app = PresupuestosAppGUI(root)
    root.mainloop()