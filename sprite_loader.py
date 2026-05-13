import os
from PyQt6.QtGui import QPixmap, QTransform
from PyQt6.QtCore import Qt

class SpriteLoader:
    """
    Loads and manages PNG sprite frames for the mascot using descriptive folder structure.
    """
    
    def __init__(self, assets_dir="assests/img"):
        self.assets_dir = assets_dir
        # Map logical states to relative file paths within the assets folder
        self.mapping = {
            "idle": [
                "idle/sitting_leg_hanging_1.png",
                "idle/sitting_leg_hanging_2.png",
                "idle/sitting_leg_hanging_3.png",
                "idle/sitting_leg_hanging_4.png"
            ],
            "sit": [
                "idle/sitting_wonderIng_rightSide.png"
            ],
            "walk": [
                "walking - running/walking_1.png",
                "walking - running/walking_2.png",
                "walking - running/walking_3.png"
            ],
            "run": [
                "walking - running/happy_runnig_1.png",
                "walking - running/happy_running_2.png"
            ],
            "drag": [
                "drag/drag_holding.png",
                "drag/drag_holding_2.png"
            ],
            "drop": [
                "drop/drop_1.png",
                "drop/drop_2.png",
                "drop/drop_3.png"
            ],
            "sleep": [
                "idle/sleeping_1.png",
                "idle/sleeping_2.png"
            ],
            "dialog": [
                "dialogbox/dialog1.png",
                "dialogbox/dialog2.png"
            ]
        }
        self.cache = {}

    def get_frames(self, state, direction="left"):
        """
        Returns a list of QPixmap frames for a given state and direction.
        Will flip images horizontally if direction is 'right'.
        """
        cache_key = f"{state}_{direction}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        file_paths = self.mapping.get(state, [])
        frames = []
        
        for rel_path in file_paths:
            full_path = os.path.join(self.assets_dir, rel_path)
            if os.path.exists(full_path):
                pixmap = QPixmap(full_path)
                
                # Assume original sprites face LEFT. 
                # If direction is RIGHT, flip horizontally.
                if direction == "right":
                    pixmap = pixmap.transformed(QTransform().scale(-1, 1))
                
                frames.append(pixmap)
            else:
                pass

        # Fallback
        if not frames:
            frames = [QPixmap()]
            
        self.cache[cache_key] = frames
        return frames

# Simple test block
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    loader = SpriteLoader()
    idle_frames = loader.get_frames("idle")
    walk_right_frames = loader.get_frames("walk", "right")
