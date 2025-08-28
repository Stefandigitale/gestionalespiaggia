import sys
import sqlite3
import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QDialog, QFormLayout, QLineEdit, 
    QMessageBox, QDateEdit, QInputDialog, QGraphicsLineItem,
    QLabel, QSpinBox, QFrame
)
from PyQt5.QtGui import QColor, QBrush, QPen, QFont, QPainter, QTextOption
from PyQt5.QtCore import Qt, QDate, pyqtSignal, QTimer

# --- MODELLO DATI: Gestisce solo la logica del database ---
class DatabaseManager:
    def __init__(self, db_name="beach_bookings.db"):
        self.db_name = db_name
        self._create_connection()

    def _create_connection(self):
        try:
            self.conn = sqlite3.connect(self.db_name)
            self.cursor = self.conn.cursor()
            self._create_tables()
        except sqlite3.Error as e:
            QMessageBox.critical(None, "Database Error", f"Could not connect to database: {e}")
            self.conn = None

    def _create_tables(self):
        if not self.conn: return
        # Tabella per le prenotazioni degli ombrelloni
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_date TEXT NOT NULL,
                cell_key TEXT NOT NULL,
                client_name_full TEXT,
                arrival_time_full TEXT,
                phone_number_full TEXT,
                staff_name_full TEXT,
                client_name_morning TEXT,
                arrival_time_morning TEXT,
                phone_number_morning TEXT,
                staff_name_morning TEXT,
                client_name_afternoon TEXT,
                arrival_time_afternoon TEXT,
                phone_number_afternoon TEXT,
                staff_name_afternoon TEXT,
                UNIQUE(booking_date, cell_key)
            )
        """)
        # Tabella per i noleggi SUP
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS sup_rentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                sup_count INTEGER NOT NULL,
                start_time_iso TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def get_bookings_for_date(self, date_str):
        if not self.conn: return {}
        bookings = {}
        show_warning = True
        try:
            self.cursor.execute("SELECT * FROM bookings WHERE booking_date = ?", (date_str,))
            for row in self.cursor.fetchall():
                if len(row) < 15:
                    if show_warning:
                        QMessageBox.warning(None, "Database Obsoleto", "Rilevata una struttura del database non aggiornata. Alcune prenotazioni potrebbero non essere visualizzate.\n\nPer favore, usa il pulsante 'Reset Database' per risolvere il problema.")
                        show_warning = False
                    continue

                key = row[2]
                bookings[key] = {
                    'full_day': {'name': row[3], 'time': row[4], 'phone': row[5], 'staff': row[6]},
                    'morning': {'name': row[7], 'time': row[8], 'phone': row[9], 'staff': row[10]},
                    'afternoon': {'name': row[11], 'time': row[12], 'phone': row[13], 'staff': row[14]}
                }
        except sqlite3.Error as e:
            print(f"Error fetching data: {e}")
            if "no such column" in str(e) and show_warning:
                 QMessageBox.warning(None, "Database Obsoleto", "La struttura del database è cambiata. Per favore, usa il pulsante 'Reset Database' per aggiornarla.")
        return bookings

    def save_booking(self, date_str, cell_key, data):
        if not self.conn: return
        try:
            self.cursor.execute("DELETE FROM bookings WHERE booking_date = ? AND cell_key = ?", (date_str, cell_key))
            
            is_full_day = any(v for k, v in data['full_day'].items() if k != 'staff')
            is_morning = any(v for k, v in data['morning'].items() if k != 'staff')
            is_afternoon = any(v for k, v in data['afternoon'].items() if k != 'staff')

            if is_full_day or is_morning or is_afternoon:
                params = (
                    date_str, cell_key,
                    data['full_day']['name'], data['full_day']['time'], data['full_day']['phone'], data['full_day']['staff'],
                    data['morning']['name'], data['morning']['time'], data['morning']['phone'], data['morning']['staff'],
                    data['afternoon']['name'], data['afternoon']['time'], data['afternoon']['phone'], data['afternoon']['staff']
                )
                self.cursor.execute("""
                    INSERT INTO bookings (
                        booking_date, cell_key, 
                        client_name_full, arrival_time_full, phone_number_full, staff_name_full,
                        client_name_morning, arrival_time_morning, phone_number_morning, staff_name_morning,
                        client_name_afternoon, arrival_time_afternoon, phone_number_afternoon, staff_name_afternoon
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, params)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error saving data: {e}")

    # --- FUNZIONI PER I SUP ---
    def get_active_rentals(self):
        if not self.conn: return []
        try:
            self.cursor.execute("SELECT id, client_name, sup_count, start_time_iso FROM sup_rentals")
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error fetching rentals: {e}")
            return []

    def start_rental(self, name, count, start_time):
        if not self.conn: return
        try:
            self.cursor.execute("INSERT INTO sup_rentals (client_name, sup_count, start_time_iso) VALUES (?, ?, ?)",
                                (name, count, start_time.isoformat()))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error starting rental: {e}")

    def end_rental(self, rental_id):
        if not self.conn: return
        try:
            self.cursor.execute("DELETE FROM sup_rentals WHERE id = ?", (rental_id,))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error ending rental: {e}")

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def reset(self):
        self.close()
        try:
            if os.path.exists(self.db_name):
                os.remove(self.db_name)
            self._create_connection()
            return True
        except Exception as e:
            QMessageBox.critical(None, "Errore Reset", f"Impossibile eliminare il file del database: {e}")
            return False

# --- FINESTRA DI DIALOGO PER INSERIMENTO DATI ---
class BookingDetailsDialog(QDialog):
    def __init__(self, parent=None, cell_number="", initial_data=None):
        super().__init__(parent)
        self.setWindowTitle(f"Dettagli Prenotazione - Postazione {cell_number}")
        self.setModal(True)
        self.setFixedSize(350, 230)
        self.data = initial_data or {'name': '', 'time': '', 'phone': '', 'staff': ''}
        self.result_data = None
        
        layout = QFormLayout()
        self.name_input = QLineEdit(self.data.get('name', ''))
        layout.addRow("Nominativo Cliente:", self.name_input)
        self.time_input = QLineEdit(self.data.get('time', ''))
        layout.addRow("Orario di Arrivo:", self.time_input)
        self.phone_input = QLineEdit(self.data.get('phone', ''))
        layout.addRow("Numero di Telefono:", self.phone_input)
        self.staff_input = QLineEdit(self.data.get('staff', ''))
        layout.addRow("Presa da:", self.staff_input)
        
        save_button = QPushButton("Salva")
        save_button.clicked.connect(self.accept_data)
        cancel_button = QPushButton("Annulla")
        cancel_button.clicked.connect(self.reject)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addRow(button_layout)
        
        self.setLayout(layout)

    def accept_data(self):
        self.result_data = {
            'name': self.name_input.text().strip(),
            'time': self.time_input.text().strip(),
            'phone': self.phone_input.text().strip(),
            'staff': self.staff_input.text().strip()
        }
        self.accept()

    def get_data(self):
        return self.result_data

# --- GESTIONE NOLEGGIO SUP ---
class RentalCard(QFrame):
    end_rental_signal = pyqtSignal(object)

    def __init__(self, rental_id, name, sup_count, start_time, parent=None):
        super().__init__(parent)
        self.rental_id = rental_id
        self.name = name
        self.sup_count = sup_count
        self.start_time = start_time

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("background-color: #e3f2fd; border-radius: 5px;")
        
        layout = QHBoxLayout(self)
        info_text = f"<b>{name}</b> ({sup_count} SUP) - Partenza: {start_time.strftime('%H:%M')}"
        layout.addWidget(QLabel(info_text))
        layout.addStretch()
        
        self.timer_label = QLabel("Tempo: 00:00:00")
        layout.addWidget(self.timer_label)
        
        end_button = QPushButton("Termina Noleggio")
        end_button.setStyleSheet("background-color: #ef5350; color: white;")
        end_button.clicked.connect(self.end_rental)
        layout.addWidget(end_button)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)
        self.update_timer()

    def update_timer(self):
        elapsed = datetime.now() - self.start_time
        elapsed_str = str(elapsed).split('.')[0]
        self.timer_label.setText(f"Tempo: {elapsed_str}")

    def end_rental(self):
        self.timer.stop()
        self.end_rental_signal.emit(self)

class SupRentalDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowTitle("Gestione Noleggio SUP")
        self.setMinimumSize(700, 500)
        
        main_layout = QVBoxLayout(self)
        
        new_rental_frame = QFrame()
        new_rental_frame.setFrameShape(QFrame.StyledPanel)
        new_rental_layout = QHBoxLayout(new_rental_frame)
        
        new_rental_layout.addWidget(QLabel("<b>Nuovo Noleggio:</b>"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nome Cliente")
        new_rental_layout.addWidget(self.name_input)
        
        self.sup_count_input = QSpinBox()
        self.sup_count_input.setMinimum(1)
        self.sup_count_input.setPrefix("N° SUP: ")
        new_rental_layout.addWidget(self.sup_count_input)
        
        start_button = QPushButton("Inizia Noleggio")
        start_button.setStyleSheet("background-color: #66bb6a; color: white;")
        start_button.clicked.connect(self.start_new_rental)
        new_rental_layout.addWidget(start_button)
        
        main_layout.addWidget(new_rental_frame)
        
        main_layout.addWidget(QLabel("<b>Noleggi Attivi:</b>"))
        self.active_rentals_layout = QVBoxLayout()
        main_layout.addLayout(self.active_rentals_layout)
        main_layout.addStretch()

        self.load_active_rentals()

    def load_active_rentals(self):
        for i in reversed(range(self.active_rentals_layout.count())): 
            self.active_rentals_layout.itemAt(i).widget().setParent(None)

        rentals = self.db_manager.get_active_rentals()
        for rental_id, name, sup_count, start_time_iso in rentals:
            start_time = datetime.fromisoformat(start_time_iso)
            card = RentalCard(rental_id, name, sup_count, start_time)
            card.end_rental_signal.connect(self.handle_end_rental)
            self.active_rentals_layout.addWidget(card)

    def start_new_rental(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Dati Mancanti", "Inserire il nome del cliente.")
            return
            
        sup_count = self.sup_count_input.value()
        start_time = datetime.now()
        
        self.db_manager.start_rental(name, sup_count, start_time)
        
        self.name_input.clear()
        self.sup_count_input.setValue(1)
        self.load_active_rentals()

    def handle_end_rental(self, card):
        self.db_manager.end_rental(card.rental_id)
        
        elapsed = datetime.now() - card.start_time
        total_minutes = elapsed.total_seconds() / 60
        price_per_hour = 10.0
        total_cost = (total_minutes / 60) * price_per_hour
        duration_str = str(elapsed).split('.')[0]
        
        QMessageBox.information(self, "Noleggio Terminato", 
            f"Cliente: <b>{card.name}</b>\n"
            f"Durata: <b>{duration_str}</b>\n\n"
            f"<b>Totale da Pagare: {total_cost:.2f} €</b>")
            
        card.setParent(None)
        card.deleteLater()

# --- VISTA: La casella grafica (NON MODIFICATA) ---
class BookingCellItem(QGraphicsRectItem):
    def __init__(self, r, c, wing, cell_number, parent=None):
        super().__init__(0, 0, 150, 150, parent)
        self.r, self.c, self.wing = r, c, wing
        self.cell_number = cell_number
        self.cell_key = f"{wing}-{r}-{c}" 
        
        self.setPen(QPen(QColor("black"), 2))
        self.setAcceptHoverEvents(True)

        self.cell_number_text = QGraphicsTextItem(str(self.cell_number), self)
        font = QFont("Sans Serif", 12, QFont.Bold)
        self.cell_number_text.setFont(font)
        self.cell_number_text.setDefaultTextColor(QColor("#424242"))
        text_rect = self.cell_number_text.boundingRect()
        self.cell_number_text.setPos(self.rect().width() - text_rect.width() - 5, self.rect().height() - text_rect.height() - 5)
        self.cell_number_text.setZValue(10)

    def update_display(self, data):
        for item in self.childItems():
            if item != self.cell_number_text:
                item.setParentItem(None)
                del item

        is_full_day = any(v for k, v in data['full_day'].items() if k != 'staff')
        is_morning = any(v for k, v in data['morning'].items() if k != 'staff')
        is_afternoon = any(v for k, v in data['afternoon'].items() if k != 'staff')

        if is_full_day:
            self.setBrush(QColor("#a5d6a7"))
            self._draw_full_day_text(self._format_text(data['full_day']))
        elif is_morning or is_afternoon:
            self.setBrush(QColor("#fff59d"))
            self._draw_half_day(
                self._format_text(data['morning']),
                self._format_text(data['afternoon'])
            )
        else:
            self.setBrush(QColor("#cfd8dc"))

    def _format_text(self, data):
        lines = []
        if data.get('name'): lines.append(data['name'])
        if data.get('time'): lines.append(f"h: {data['time']}")
        if data.get('phone'): lines.append(f"tel: {data['phone']}")
        if data.get('staff'): lines.append(f"by: {data['staff']}")
        return "\n".join(lines)

    def _draw_full_day_text(self, text):
        text_item = QGraphicsTextItem(text, self)
        font = QFont("Sans Serif", 12)
        font.setBold(True)
        text_item.setFont(font)
        
        option = QTextOption(Qt.AlignCenter)
        text_item.document().setDefaultTextOption(option)
        text_item.setTextWidth(self.rect().width())
        
        text_rect = text_item.boundingRect()
        text_item.setPos(0, (self.rect().height() - text_rect.height()) / 2)

    def _draw_half_day(self, morning_text, afternoon_text):
        line = QGraphicsLineItem(self.rect().topRight().x(), self.rect().topRight().y(), self.rect().bottomLeft().x(), self.rect().bottomLeft().y(), self)
        line.setPen(QPen(QColor("black"), 2))
        
        if morning_text:
            morning_item = QGraphicsTextItem(morning_text, self)
            font = QFont("Sans Serif", 9)
            font.setBold(True)
            morning_item.setFont(font)
            morning_item.setTextWidth(90)
            
            text_rect = morning_item.boundingRect()
            morning_item.setTransformOriginPoint(text_rect.center())
            morning_item.setRotation(-45)
            
            center_x = self.rect().width() * 0.70
            center_y = self.rect().height() * 0.30
            morning_item.setPos(center_x - text_rect.width() / 1, center_y - text_rect.height() / 1.6)

        if afternoon_text:
            afternoon_item = QGraphicsTextItem(afternoon_text, self)
            font = QFont("Sans Serif", 9)
            font.setBold(True)
            afternoon_item.setFont(font)
            afternoon_item.setTextWidth(90)

            text_rect = afternoon_item.boundingRect()
            afternoon_item.setTransformOriginPoint(text_rect.center())
            afternoon_item.setRotation(-45)
            
            center_x = self.rect().width() * 0.45
            center_y = self.rect().height() * 0.70
            afternoon_item.setPos(center_x - text_rect.width() / 20, center_y - text_rect.height() / 1.6)

    def hoverEnterEvent(self, event):
        self.setBrush(QColor("#bbdefb"))
        
    def hoverLeaveEvent(self, event):
        if self.scene() and self.scene().parent():
            self.scene().parent().update_cell_display(self.cell_key)

# --- CONTROLLER: La griglia ---
class BookingGridWidget(QGraphicsView):
    cellClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        
        self.LEFT_WING_ROWS, self.LEFT_WING_COLS = 4, 6
        self.RIGHT_WING_ROWS, self.RIGHT_WING_COLS = 3, 4
        
        self.cells_items = {} 
        self.cells_data = {}  
        
        self._draw_grid()

    def _draw_grid(self):
        self.scene().clear()
        self.cells_items.clear()
        
        y_offset = 15
        for r in range(self.LEFT_WING_ROWS):
            x_offset = 15
            for c in range(self.LEFT_WING_COLS):
                cell_number = self._get_cell_number(r, c, "left")
                item = BookingCellItem(r, c, "left", cell_number)
                item.setPos(x_offset, y_offset)
                self.scene().addItem(item)
                self.cells_items[item.cell_key] = item
                x_offset += 150
            y_offset += 150

        y_offset = 15
        for r in range(self.RIGHT_WING_ROWS):
            x_offset = 15 + (self.LEFT_WING_COLS * 150) + 80
            for c in range(self.RIGHT_WING_COLS):
                cell_number = self._get_cell_number(r, c, "right")
                item = BookingCellItem(r, c, "right", cell_number)
                item.setPos(x_offset, y_offset)
                self.scene().addItem(item)
                self.cells_items[item.cell_key] = item
                x_offset += 150
            y_offset += 150

    def _get_cell_number(self, r, c, wing):
        if wing == "left":
            return (r + 1) * 10 + c
        elif wing == "right":
            return (r + 1) * 10 + 6 + c
        return 0
    
    def get_empty_booking_data(self):
        return {
            'full_day': {'name': '', 'time': '', 'phone': '', 'staff': ''},
            'morning': {'name': '', 'time': '', 'phone': '', 'staff': ''},
            'afternoon': {'name': '', 'time': '', 'phone': '', 'staff': ''}
        }

    def load_day_data(self, bookings_from_db):
        self.cells_data.clear()
        for key, item in self.cells_items.items():
            self.cells_data[key] = bookings_from_db.get(key, self.get_empty_booking_data())
            item.update_display(self.cells_data[key])
            
    def update_cell_display(self, cell_key):
        if cell_key in self.cells_items and cell_key in self.cells_data:
            self.cells_items[cell_key].update_display(self.cells_data[cell_key])

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if isinstance(item, BookingCellItem):
            self.cellClicked.emit(item.cell_key)
        super().mousePressEvent(event)

# --- Finestra Principale ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestore Prenotazioni Spiaggia")
        self.showMaximized()
        self.db_manager = DatabaseManager()
        self.current_date = QDate.currentDate()
        self.sup_rental_dialog = None
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        
        self._create_ui()
        self.load_current_date_bookings()

    def _create_ui(self):
        nav_layout = QHBoxLayout()
        nav_layout.setAlignment(Qt.AlignCenter)
        self.date_edit = QDateEdit(self.current_date)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self.load_current_date_bookings)
        prev_button = QPushButton("<< Giorno Prec.")
        prev_button.clicked.connect(lambda: self.date_edit.setDate(self.date_edit.date().addDays(-1)))
        next_button = QPushButton("Giorno Succ. >>")
        next_button.clicked.connect(lambda: self.date_edit.setDate(self.date_edit.date().addDays(1)))
        
        sup_button = QPushButton("Noleggio SUP")
        sup_button.setStyleSheet("background-color: #29b6f6; color: white; font-weight: bold; padding: 5px;")
        sup_button.clicked.connect(self.open_sup_rental)
        
        reset_button = QPushButton("Reset Database")
        reset_button.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; padding: 5px;")
        reset_button.clicked.connect(self.reset_database)

        nav_layout.addWidget(prev_button)
        nav_layout.addWidget(self.date_edit)
        nav_layout.addWidget(next_button)
        nav_layout.addSpacing(50)
        nav_layout.addWidget(sup_button)
        nav_layout.addWidget(reset_button)
        self.main_layout.addLayout(nav_layout)

        self.grid_view = BookingGridWidget(self)
        self.grid_view.cellClicked.connect(self.handle_cell_click)
        self.main_layout.addWidget(self.grid_view)

    def open_sup_rental(self):
        if not self.sup_rental_dialog:
            self.sup_rental_dialog = SupRentalDialog(self.db_manager, self)
            self.sup_rental_dialog.finished.connect(self.on_sup_dialog_closed)
            self.sup_rental_dialog.show()
        else:
            self.sup_rental_dialog.activateWindow()

    def on_sup_dialog_closed(self):
        self.sup_rental_dialog = None

    def load_current_date_bookings(self):
        self.current_date = self.date_edit.date()
        date_str = self.current_date.toString(Qt.ISODate)
        bookings = self.db_manager.get_bookings_for_date(date_str)
        self.grid_view.load_day_data(bookings)

    def handle_cell_click(self, cell_key):
        cell_data = self.grid_view.cells_data[cell_key]
        
        is_booked = any(v for k, v in cell_data['full_day'].items() if k != 'staff') or \
                    any(v for k, v in cell_data['morning'].items() if k != 'staff') or \
                    any(v for k, v in cell_data['afternoon'].items() if k != 'staff')

        if not is_booked:
            self._create_new_booking(cell_key)
        else:
            self._manage_existing_booking(cell_key)
    
    def _create_new_booking(self, cell_key):
        cell_number = self.grid_view.cells_items[cell_key].cell_number
        items = ["Giornata Intera", "Mezza Giornata"]
        item, ok = QInputDialog.getItem(self, "Nuova Prenotazione", f"Postazione {cell_number}:", items, 0, False)
        if not ok or not item: return

        if item == "Giornata Intera":
            details = self._get_booking_details(cell_number)
            if details: 
                self.grid_view.cells_data[cell_key]['full_day'] = details
                self._save_and_update(cell_key)
        else:
            slots = ["Mattina", "Pomeriggio"]
            slot, ok_slot = QInputDialog.getItem(self, "Mezza Giornata", f"Postazione {cell_number}:", slots, 0, False)
            if ok_slot and slot:
                details = self._get_booking_details(cell_number)
                if details:
                    if slot == "Mattina": self.grid_view.cells_data[cell_key]['morning'] = details
                    else: self.grid_view.cells_data[cell_key]['afternoon'] = details
                    self._save_and_update(cell_key)
    
    def _manage_existing_booking(self, cell_key):
        cell_number = self.grid_view.cells_items[cell_key].cell_number
        data = self.grid_view.cells_data[cell_key]
        is_full_day = any(v for k, v in data['full_day'].items() if k != 'staff')

        actions = []
        if is_full_day:
            actions.append("Modifica/Cancella Giornata Intera")
        else:
            if any(v for k, v in data['morning'].items() if k != 'staff'): actions.append("Modifica/Cancella Mattina")
            else: actions.append("Prenota Mattina")
            if any(v for k, v in data['afternoon'].items() if k != 'staff'): actions.append("Modifica/Cancella Pomeriggio")
            else: actions.append("Prenota Pomeriggio")
        
        action, ok = QInputDialog.getItem(self, "Gestione Prenotazione", f"Postazione {cell_number}:", actions, 0, False)
        if not ok or not action: return

        if "Giornata Intera" in action:
            new_details = self._get_booking_details(cell_number, data['full_day'])
            self.grid_view.cells_data[cell_key]['full_day'] = new_details or self.grid_view.get_empty_booking_data()['full_day']
        elif "Mattina" in action:
            new_details = self._get_booking_details(cell_number, data['morning'])
            self.grid_view.cells_data[cell_key]['morning'] = new_details or self.grid_view.get_empty_booking_data()['morning']
        elif "Pomeriggio" in action:
            new_details = self._get_booking_details(cell_number, data['afternoon'])
            self.grid_view.cells_data[cell_key]['afternoon'] = new_details or self.grid_view.get_empty_booking_data()['afternoon']
        
        self._save_and_update(cell_key)

    def _get_booking_details(self, cell_number, initial_data=None):
        dialog = BookingDetailsDialog(self, str(cell_number), initial_data)
        if dialog.exec_() == QDialog.Accepted:
            details = dialog.get_data()
            if any(v for k, v in details.items() if k != 'staff'):
                return details
            elif initial_data: 
                if QMessageBox.question(self, "Conferma", "Cancellare la prenotazione?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                    return None 
                return initial_data 
        return initial_data 

    def _save_and_update(self, cell_key):
        date_str = self.current_date.toString(Qt.ISODate)
        self.db_manager.save_booking(date_str, cell_key, self.grid_view.cells_data[cell_key])
        self.grid_view.update_cell_display(cell_key)

    def reset_database(self):
        reply = QMessageBox.question(self, 'Conferma Reset', "Cancellare TUTTE le prenotazioni?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.db_manager.reset():
                QMessageBox.information(self, "Successo", "Database resettato.")
                self.load_current_date_bookings()

    def closeEvent(self, event):
        self.db_manager.close()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
