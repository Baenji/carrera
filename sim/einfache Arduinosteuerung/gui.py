# Elementare Steuerung mittels Slider

import dearpygui.dearpygui as dpg
from arduinosteuerung import ArduinoInterface


def slider_callback(sender, app_data):
    arduino.set_signal_rate(app_data)
    #dpg.set_value("value_text", f"{app_data}") # Feld "value_text" ist nicht mehr vorhanden

def stop_callback(sender):
    arduino.close()
    dpg.stop_dearpygui()



if __name__ == "__main__":
    dpg.create_context()
    arduino = ArduinoInterface()

    # -------- Theme (modernere Optik) --------
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 8)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 6)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 10)

    dpg.bind_theme(global_theme)

    # -------- Fenster --------
    dpg.create_viewport(title="Parameter Tool", width=700, height=300)

    with dpg.window(tag="main_window", no_title_bar=True):

        dpg.add_spacer(height=10)

        # Titel
        dpg.add_text(f"Arduino on Port: {arduino.serial_connection.portstr}") # or port instead of portstr
        dpg.add_spacer(height=30)

        dpg.add_text("Speed einstellen (Prozent der vollen Spannung)")
        dpg.add_spacer(height=30)

        # sehr breiter Slider
        dpg.add_slider_int(
            label="",
            min_value=0,
            max_value=100,
            default_value=0,
            width=-1,                 # nutzt komplette verfügbare Breite
            callback=slider_callback
        )

        dpg.add_spacer(height=20)

        #dpg.add_button(label="Beenden", callback=lambda: dpg.stop_dearpygui())
        dpg.add_button(label="Beenden", callback=stop_callback)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main_window", True)
    dpg.start_dearpygui()
    dpg.destroy_context()
