import os
import random
from PyQt6.QtCore import QObject, QTimer, Qt
from PyQt6.QtGui import QPixmap

class BehaviorScheduler(QObject):
    def __init__(self, assets_dir="assests/img", set_frame_callback=None, behavior_changed_callback=None):
        super().__init__()
        self.assets_dir = assets_dir
        self.set_frame_callback = set_frame_callback
        self.behavior_changed_callback = behavior_changed_callback
        
        self.current_behavior = None
        self.current_behavior_name = None
        self.current_frame_index = 0
        self.current_loop = 0
        self.behavior_history = []
        self.is_sleeping = False
        self.is_active = False
        self.is_dialog_active = False
        self.on_wake_up_callback = None
        
        # Timers
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self._next_frame)
        
        self.pause_timer = QTimer()
        self.pause_timer.setSingleShot(True)
        self.pause_timer.timeout.connect(self._pick_next_idle_behavior)
        
        self.hold_timer = QTimer()
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self._on_behavior_step_finished)

        self.idle_check_timer = QTimer()
        self.idle_check_timer.timeout.connect(self._check_user_idle)
        
        self.user_idle_seconds = 0
        
        self.idle_behaviors = [
            {
                "name": "leg_hanging",
                "subdir": "idle",
                "frames": ["sitting_leg_hanging_1.png", "sitting_leg_hanging_2.png",
                           "sitting_leg_hanging_3.png", "sitting_leg_hanging_4.png"],
                "fps": 4, # Reduced FPS
                "loop": True,
                "loop_count_range": (3, 6), # Loop for longer
                "weight": 30
            },
            {
                "name": "smirking",
                "subdir": "idle",
                "frames": ["sitting_smirking.png"],
                "fps": 1,
                "loop": False,
                "hold_range": (1.5, 3.0),
                "weight": 10
            },
            {
                "name": "wondering_left",
                "subdir": "idle",
                "frames": ["sitting_wondering_leftSide1.png", 
                           "sittiing_wondering_leftSide2.png"], # Fixed typo from assets
                "fps": 4,
                "loop": True,
                "loop_count_range": (1, 3),
                "weight": 15
            },
            {
                "name": "wondering_right",
                "subdir": "idle",
                "frames": ["sitting_wonderIng_rightSide.png",
                           "sitting_wonderIng_littleLess_rightSide.png"],
                "fps": 4,
                "loop": True,
                "loop_count_range": (1, 3),
                "weight": 15
            },
            {
                "name": "pulling",
                "subdir": "idle",
                "frames": [f"pulling_MiniMiko_{i}.png" for i in range(1, 11)],
                "fps": 5, # Reduced FPS
                "loop": False,
                "weight": 20,
                "custom_pull_loop": True # Flag for custom logic
            },
            {
                "name": "sleeping",
                "subdir": "idle",
                "frames": ["sleeping_1.png", "sleeping_2.png"],
                "fps": 2,
                "loop": True,
                "loop_count_range": (3, 6),
                "weight": 10,
                "min_idle_seconds": 120
            },
            {
                "name": "walk",
                "subdir": "walking - running",
                "frames": ["walking_1.png", "walking_2.png", "walking_3.png"],
                "fps": 8,
                "loop": True,
                "loop_count_range": (2, 4),
                "weight": 15
            },
        ]

        # Extra behaviors not in the random idle rotation
        self.extra_behaviors = [
            {
                "name": "run",
                "subdir": "walking - running",
                "frames": ["happy_runnig_1.png", "happy_running_2.png"],
                "fps": 12,
                "loop": True
            },
            {
                "name": "run_transition",
                "subdir": "walking - running",
                "frames": ["happy_running_wait_somethingHappend.png"],
                "fps": 6,
                "loop": False
            },
            {
                "name": "stop_run",
                "subdir": "walking - running",
                "frames": ["running_about_toStop.png", "about_toStop_2.png", "standStill_AfterRunning.png"],
                "fps": 8,
                "loop": False
            },
            {
                "name": "turn",
                "subdir": "walking - running",
                "frames": ["changing_direction.png"],
                "fps": 6,
                "loop": False
            },
            {
                "name": "dialog",
                "subdir": "dialogbox",
                "frames": ["dialog1.png", "dialog2.png"],
                "fps": 2,
                "loop": True
            },
            {
                "name": "dialog_holding",
                "subdir": "dialogbox",
                "frames": ["dialog_holding.png"],
                "fps": 1,
                "loop": False
            },
            {
                "name": "sitting",
                "subdir": "idle",
                "frames": ["sitting_smirking.png"],
                "fps": 1,
                "loop": False
            }
        ]

    def start(self):
        self.is_active = True
        self.idle_check_timer.start(1000)
        self._pick_next_idle_behavior()

    def stop(self):
        self.is_active = False
        self.anim_timer.stop()
        self.pause_timer.stop()
        self.hold_timer.stop()
        self.idle_check_timer.stop()

    def update_activity(self):
        if self.is_sleeping:
            self.is_sleeping = False
            if self.on_wake_up_callback:
                self.on_wake_up_callback()
            else:
                self.force_behavior("leg_hanging")
        self.user_idle_seconds = 0

    def _check_user_idle(self):
        self.user_idle_seconds += 1

    def force_behavior(self, name, custom_behavior=None):
        self.anim_timer.stop()
        self.pause_timer.stop()
        self.hold_timer.stop()
        
        if custom_behavior:
            self._play_behavior(custom_behavior)
            return

        # Search in both lists
        for b in self.idle_behaviors + self.extra_behaviors:
            if b["name"] == name:
                behavior = b.copy()
                if "loop_count_range" in b:
                    behavior["loop_count"] = random.randint(*b["loop_count_range"])
                self._play_behavior(behavior)
                return
        
        pass

    def _pick_next_idle_behavior(self):
        if not self.is_active or self.is_dialog_active: return

        available_behaviors = []
        weights = []

        for b in self.idle_behaviors:
            if b["name"] == self.current_behavior_name:
                continue
            
            # CRITICAL: If user is NOT idle, they should NEVER pick the sleeping behavior
            # This ensures she stays 'awake' while you work.
            if b["name"] == "sleeping":
                if self.user_idle_seconds < b.get("min_idle_seconds", 120):
                    continue
                else:
                    weight = 80 # Highly likely to sleep if idle for long
            else:
                weight = b["weight"]
            
            if b["name"] in self.behavior_history:
                weight *= 0.5
            
            available_behaviors.append(b)
            weights.append(weight)

        if not available_behaviors:
            # Fallback to a safe neutral state
            self.force_behavior("sitting")
            return
        
        next_b = random.choices(available_behaviors, weights=weights, k=1)[0]

        behavior = next_b.copy()
        if "loop_count_range" in behavior:
            behavior["loop_count"] = random.randint(*behavior["loop_count_range"])
        if "hold_range" in behavior:
            behavior["hold_seconds"] = random.uniform(*behavior["hold_range"])

        self.current_behavior_name = behavior["name"]
        self.behavior_history.append(self.current_behavior_name)
        if len(self.behavior_history) > 3:
            self.behavior_history.pop(0)

        if behavior["name"] == "sleeping":
            self.is_sleeping = True

        self._play_behavior(behavior)

    def _play_behavior(self, behavior):
        self.current_behavior = behavior
        self.current_behavior_name = behavior["name"]
        self.current_frame_index = 0
        self.current_loop = 0
        
        if self.behavior_changed_callback:
            self.behavior_changed_callback(behavior["name"])
            
        self._update_frame_display()
        
        if "hold_seconds" in behavior:
             self.hold_timer.start(int(behavior["hold_seconds"] * 1000))
        elif "fps" in behavior:
            interval = int(1000 / behavior["fps"])
            self.anim_timer.start(interval)

    def _next_frame(self):
        if not self.current_behavior: return
        frames = self.current_behavior["frames"]
        
        # Custom logic for 'pulling' behavior (acceleration loop between frames 6 and 7)
        if self.current_behavior_name == "pulling":
            # Index 5 is frame 6, Index 6 is frame 7
            if self.current_frame_index == 6: 
                if not hasattr(self, "_pull_subloop_total"):
                    self._pull_subloop_total = random.randint(15, 25)
                    self._pull_subloop_count = 0
                
                if self._pull_subloop_count < self._pull_subloop_total:
                    self._pull_subloop_count += 1
                    progress = self._pull_subloop_count / self._pull_subloop_total
                    new_fps = 4 + (progress * 10)
                    self.anim_timer.start(int(1000 / new_fps))
                    
                    self.current_frame_index = 4 # Toggle back so next tick shows index 5 (frame 6)
                else:
                    delattr(self, "_pull_subloop_total")
                    delattr(self, "_pull_subloop_count")
                    # Restore original behavior FPS
                    self.anim_timer.start(int(1000 / self.current_behavior.get("fps", 5)))

        # Custom logic for 'leg_hanging' (loop last 2 frames: indices 2 and 3)
        elif self.current_behavior_name == "leg_hanging":
            if self.current_frame_index == 3:
                self.current_loop += 1
                if self.current_loop < self.current_behavior.get("loop_count", 1):
                    self.current_frame_index = 1 # Toggle back so next tick shows index 2 (frame 3)

        self.current_frame_index += 1
        
        if self.current_frame_index >= len(frames):
            if self.current_behavior.get("loop"):
                self.current_loop += 1
                if self.current_loop >= self.current_behavior.get("loop_count", 1):
                    self._on_behavior_step_finished()
                    return
                else:
                    self.current_frame_index = 0
            else:
                self._on_behavior_step_finished()
                return
        self._update_frame_display()

    def _on_behavior_step_finished(self):
        self.anim_timer.stop()
        self.hold_timer.stop()
        
        # Continuous loop for movement/dialog behaviors
        if self.current_behavior_name in ["walk", "run", "dialog", "dialog_holding"]:
            self._play_behavior(self.current_behavior)
            return

        # Persistent hold for user interaction - do NOT start pause_timer
        if self.current_behavior_name == "dialog_holding":
            # Just stay on this frame, do nothing else
            return

        if self.is_dialog_active:
            self._play_behavior(self.current_behavior)
            return
            
        # Standard idle pause
        pause = random.randint(2, 6)
        self.pause_timer.start(pause * 1000)

    def _update_frame_display(self):
        if not self.current_behavior or not self.set_frame_callback: return
        frame_name = self.current_behavior["frames"][self.current_frame_index]
        subdir = self.current_behavior.get("subdir", "")
        path = os.path.join(self.assets_dir, subdir, frame_name)
        if os.path.exists(path):
            pixmap = QPixmap(path)
            self.set_frame_callback(pixmap)
        else:
            pass

    def start_dialog_animation(self):
        self.is_dialog_active = True
        self.anim_timer.stop()
        self.pause_timer.stop()
        self.hold_timer.stop()
        dialog_behavior = {
            "name": "dialog", "subdir": "dialogbox",
            "frames": ["dialog1.png", "dialog2.png"], "fps": 1.5, "loop": True
        }
        self._play_behavior(dialog_behavior)

    def stop_dialog_animation(self):
        self.is_dialog_active = False
        self._pick_next_idle_behavior()

    def play_drop_sequence(self, final_callback):
        """Problem 4: Drop sequence."""
        self.stop()
        drop_behavior = {
            "name": "drop", "subdir": "drop",
            "frames": ["drop_1.png", "drop_2.png", "drop_3.png", "drop_end.png"],
            "fps": 10, "loop": False
        }
        
        def on_drop_end():
            QTimer.singleShot(500, lambda: self._play_sleep_loop(final_callback))
            
        self.force_behavior("drop", drop_behavior)
        total_time = (len(drop_behavior["frames"]) / drop_behavior["fps"]) * 1000
        QTimer.singleShot(int(total_time) + 50, on_drop_end)

    def _play_sleep_loop(self, final_callback):
        sleep_loop = {
            "name": "sleep_post_drop", "subdir": "idle",
            "frames": ["sleeping_1.png", "sleeping_2.png"],
            "fps": 2, "loop": True, "loop_count": 3
        }
        self.force_behavior("sleep_post_drop", sleep_loop)
        total_time = (len(sleep_loop["frames"]) * sleep_loop["loop_count"] / sleep_loop["fps"]) * 1000
        QTimer.singleShot(int(total_time) + 50, final_callback)
