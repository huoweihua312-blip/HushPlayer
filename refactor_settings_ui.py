"""
Refactor SettingsDialog to use left navigation + right content layout
"""
from pathlib import Path

def read_current_file():
    """Read the current settings_dialog.py"""
    return Path('app/ui/settings_dialog.py').read_text(encoding='utf-8')

def extract_control_initializations(content):
    """Extract all control initialization code"""
    lines = content.split('\n')

    # Find all control assignments
    controls = {}
    current_control = None

    for i, line in enumerate(lines):
        if 'self.restore_checkbox' in line:
            controls['restore_checkbox'] = i
        elif 'self.auto_scan_checkbox' in line and 'auto_scan_checkbox' not in controls:
            controls['auto_scan_checkbox'] = i
        elif 'self.floating_auto_open_checkbox' in line:
            controls['floating_auto_open_checkbox'] = i
        elif 'self.appearance_mode_combo' in line and 'appearance_mode_combo' not in controls:
            controls['appearance_mode_combo'] = i
        elif 'self.immersive_background_mode_combo' in line and 'immersive_background_mode_combo' not in controls:
            controls['immersive_background_mode_combo'] = i
        elif 'self.auto_hide_checkbox' in line and 'auto_hide_checkbox' not in controls:
            controls['auto_hide_checkbox'] = i
        elif 'self.alpha_slider' in line and 'alpha_slider' not in controls:
            controls['alpha_slider'] = i
        elif 'self.floating_color_combo' in line and 'floating_color_combo' not in controls:
            controls['floating_color_combo'] = i
        elif 'self.music_scan_folder_list' in line and 'music_scan_folder_list' not in controls:
            controls['music_scan_folder_list'] = i
        elif 'self.audio_cache_summary_label' in line and 'audio_cache_summary_label' not in controls:
            controls['audio_cache_summary_label'] = i
        elif 'self.check_update_button' in line and 'check_update_button' not in controls:
            controls['check_update_button'] = i

    return controls

def main():
    content = read_current_file()
    controls = extract_control_initializations(content)

    print("Found controls:")
    for name, line_num in sorted(controls.items(), key=lambda x: x[1]):
        print(f"  {name}: line {line_num + 1}")

    print(f"\nTotal controls found: {len(controls)}")

if __name__ == '__main__':
    main()
