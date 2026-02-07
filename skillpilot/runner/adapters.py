"""
Tool adapters for SkillPilot Runner.

Adapters provide the interface to different EDA tools.
"""

import os
import pty
import subprocess
import time
from typing import Optional, List, Callable
from dataclasses import dataclass, field


@dataclass
class AdapterConfig:
    """Configuration for a tool adapter"""
    tool_name: str
    tool_version: str = "1.0"
    # Tool startup command (argv)
    command: List[str] = field(default_factory=list)
    # Boot Tcl commands to run at startup
    boot_commands: List[str] = field(default_factory=list)
    # Working directory for the tool
    workdir: str = field(default_factory=lambda: os.getcwd())


class ToolAdapter:
    """
    Base class for tool adapters.

    Adapters manage the PTY connection to EDA tools.
    """

    def __init__(self, config: AdapterConfig):
        self.config = config
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None

    def start(self) -> int:
        """
        Start the tool process with PTY.

        Returns:
            PID of the tool process
        """
        # Open PTY
        self.master_fd, self.slave_fd = pty.openpty()

        # Start process with slave PTY as stdin/stdout/stderr
        self.process = subprocess.Popen(
            self.config.command,
            stdin=self.slave_fd,
            stdout=self.slave_fd,
            stderr=self.slave_fd,
            cwd=self.config.workdir,
            close_fds=True,
            preexec_fn=os.setsid,  # New process group
        )

        # Close slave FD (we use master)
        os.close(self.slave_fd)
        self.slave_fd = None

        self.pid = self.process.pid

        # Wait for tool to be ready (simple approach: give it time to start)
        time.sleep(0.5)

        # Run boot commands
        for cmd in self.config.boot_commands:
            self.write(cmd)

        return self.pid

    def write(self, data: str) -> None:
        """
        Write data to the tool.

        Args:
            data: Text to write to tool stdin
        """
        if self.master_fd is None:
            raise RuntimeError("Tool not started")

        os.write(self.master_fd, data.encode('utf-8'))

    def read(self, timeout: float = 0.1, size: int = 4096) -> bytes:
        """
        Read data from the tool.

        Args:
            timeout: Read timeout in seconds
            size: Maximum bytes to read

        Returns:
            Data read from tool stdout/stderr
        """
        if self.master_fd is None:
            raise RuntimeError("Tool not started")

        import select
        ready, _, _ = select.select([self.master_fd], [], [], timeout)

        if ready:
            return os.read(self.master_fd, size)
        return b''

    def send_signal(self, signal: int) -> None:
        """
        Send a signal to the tool process.

        Args:
            signal: Signal number (e.g., signal.SIGINT, signal.SIGTERM)
        """
        if self.process is None:
            raise RuntimeError("Tool not started")

        # Send signal to process group
        try:
            os.killpg(os.getpgid(self.process.pid), signal)
        except ProcessLookupError:
            pass  # Process already terminated

    def terminate(self) -> None:
        """Terminate the tool process gracefully"""
        if self.process is not None:
            import signal
            self.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.kill()

    def kill(self) -> None:
        """Force kill the tool process"""
        if self.process is not None:
            import signal
            self.send_signal(signal.SIGKILL)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    def close(self) -> None:
        """Close PTY and cleanup"""
        if self.master_fd is not None:
            os.close(self.master_fd)
            self.master_fd = None
        if self.slave_fd is not None:
            os.close(self.slave_fd)
            self.slave_fd = None

    def is_alive(self) -> bool:
        """Check if the tool process is still running"""
        if self.process is None:
            return False
        return self.process.poll() is None


class DemoToolAdapter(ToolAdapter):
    """
    Adapter for the demo_tool (mock EDA tool).

    Demo tool path: examples/tools/demo_tool.py
    """

    @classmethod
    def create(cls, workdir: Optional[str] = None) -> "DemoToolAdapter":
        """Create a DemoTool adapter with default config"""
        # Find demo_tool.py
        script_dir = os.path.dirname(os.path.abspath(__file__))
        demo_tool_path = os.path.join(
            script_dir,
            "..",
            "..",
            "examples",
            "tools",
            "demo_tool.py"
        )
        demo_tool_path = os.path.abspath(demo_tool_path)

        if not os.path.exists(demo_tool_path):
            raise FileNotFoundError(f"Demo tool not found at {demo_tool_path}")

        config = AdapterConfig(
            tool_name="demo_tool",
            tool_version="1.0",
            command=["python3", demo_tool_path],
            workdir=workdir or os.getcwd(),
        )

        return cls(config)
