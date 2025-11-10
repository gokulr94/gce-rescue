"""
GCE Rescue V2 - Progress Tracking

Provides visual progress feedback for operations.
Uses tqdm if available, falls back to simple implementation.
"""

import sys
import time
from typing import Optional


class ProgressTracker:
    """
    Track progress of operations with visual feedback.

    Features:
    - Step-based progress tracking
    - Works with or without tqdm
    - Clean, professional output
    - Shows current step and total steps

    Example:
        tracker = ProgressTracker(total_steps=5, desc="Rescue Operation")
        tracker.start()

        tracker.update_step("Stopping VM")
        # ... do work ...
        tracker.advance()

        tracker.update_step("Creating disk")
        # ... do work ...
        tracker.advance()

        tracker.finish()
    """

    def __init__(self, total_steps: int, desc: str = "Operation", use_tqdm: bool = True):
        """
        Initialize progress tracker.

        Args:
            total_steps: Total number of steps in operation
            desc: Description of the operation
            use_tqdm: Whether to try using tqdm (falls back if not available)
        """
        self.total_steps = total_steps
        self.current_step = 0
        self.desc = desc
        self.current_step_name = ""
        self.start_time = None
        self.tqdm_bar = None
        self.use_tqdm = use_tqdm

        # Try to import tqdm
        if self.use_tqdm:
            try:
                from tqdm import tqdm
                self.tqdm = tqdm
                self.has_tqdm = True
            except ImportError:
                self.has_tqdm = False
        else:
            self.has_tqdm = False

    def start(self):
        """Start the progress tracker."""
        self.start_time = time.time()
        self.current_step = 0

        if self.has_tqdm:
            # Use tqdm for rich progress bar
            self.tqdm_bar = self.tqdm(
                total=self.total_steps,
                desc=self.desc,
                bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}]',
                ncols=80,
                file=sys.stdout
            )
        else:
            # Simple fallback
            print(f"┌── {self.desc}")
            print(f"│   Total steps: {self.total_steps}")

    def update_step(self, step_name: str):
        """
        Update the current step name.

        Args:
            step_name: Name of the current step
        """
        self.current_step_name = step_name

        if self.has_tqdm and self.tqdm_bar:
            self.tqdm_bar.set_description(f"{self.desc} - {step_name}")
        else:
            # Show step in simple format
            print(f"├── [{self.current_step + 1}/{self.total_steps}] {step_name}...", flush=True)

    def advance(self, steps: int = 1):
        """
        Advance the progress by one or more steps.

        Args:
            steps: Number of steps to advance (default: 1)
        """
        self.current_step += steps

        if self.has_tqdm and self.tqdm_bar:
            self.tqdm_bar.update(steps)

    def finish(self):
        """Finish the progress tracker."""
        if self.has_tqdm and self.tqdm_bar:
            self.tqdm_bar.close()
        else:
            elapsed = time.time() - self.start_time if self.start_time else 0
            print(f"└── {self.desc} completed in {elapsed:.1f}s")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.finish()
        return False


class SimpleProgressTracker:
    """
    Simple progress tracker without any fancy output.

    This is used when the user wants minimal output or
    when running in non-interactive mode.

    Example:
        tracker = SimpleProgressTracker()
        tracker.start()
        tracker.update_step("Step 1")
        tracker.advance()
        tracker.finish()
    """

    def __init__(self, total_steps: int = 0, desc: str = "Operation"):
        """
        Initialize simple tracker.

        Args:
            total_steps: Total number of steps (unused, for compatibility)
            desc: Description (unused, for compatibility)
        """
        pass

    def start(self):
        """Start tracking (no-op)."""
        pass

    def update_step(self, step_name: str):
        """Update step (no-op)."""
        pass

    def advance(self, steps: int = 1):
        """Advance progress (no-op)."""
        pass

    def finish(self):
        """Finish tracking (no-op)."""
        pass

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.finish()
        return False


def create_progress_tracker(
    total_steps: int,
    desc: str = "Operation",
    enabled: bool = True,
    use_tqdm: bool = True
) -> ProgressTracker:
    """
    Factory function to create appropriate progress tracker.

    Args:
        total_steps: Total number of steps
        desc: Description of operation
        enabled: Whether to show progress at all
        use_tqdm: Whether to try using tqdm

    Returns:
        ProgressTracker or SimpleProgressTracker instance
    """
    if not enabled:
        return SimpleProgressTracker(total_steps, desc)
    return ProgressTracker(total_steps, desc, use_tqdm)
