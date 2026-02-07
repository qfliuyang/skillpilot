"""
Pseudo-DSUB Job Submission System

Mock job submission for testing without real DSUB/LSF.
Simulates job queue management, status tracking, and result collection.
"""

import os
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from enum import Enum


class JobStatus(str, Enum):
    """Job status"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobRequest:
    """Job submission request"""
    job_id: str
    job_name: str
    command: str
    workdir: str
    stdout_path: str
    stderr_path: str
    queue: Optional[str] = None
    project: Optional[str] = None
    resource_spec: Optional[str] = None
    timeout_hours: int = 24


@dataclass
class JobInfo:
    """Job information and status"""
    job_id: str
    job_name: str
    status: JobStatus
    submit_time: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    exit_code: Optional[int] = None


class PseudoSubmitter:
    """
    Pseudo job submitter for testing without DSUB/LSF.

    Simulates:
    - Job submission to queue
    - Job status tracking
    - Job execution (via local subprocess)
    - Result file generation
    """

    def __init__(self, job_dir: str, queue_delay: float = 0.5, default_runtime: float = 2.0):
        self.job_dir = job_dir
        self.queue_delay = queue_delay
        self.default_runtime = default_runtime
        os.makedirs(job_dir, exist_ok=True)
        self.jobs: Dict[str, JobInfo] = {}

    def submit(self, request: JobRequest) -> JobInfo:
        """
        Submit a job to the pseudo queue.

        Args:
            request: Job request

        Returns:
            JobInfo with initial status
        """
        job_info = JobInfo(
            job_id=request.job_id,
            job_name=request.job_name,
            status=JobStatus.QUEUED,
            submit_time=self._get_timestamp(),
        )
        self.jobs[request.job_id] = job_info

        # Write job request to queue file
        self._write_job_request(request)

        return job_info

    def get_status(self, job_id: str) -> JobInfo:
        """
        Get job status.

        Args:
            job_id: Job ID

        Returns:
            JobInfo with current status
        """
        return self.jobs.get(job_id)

    def wait_for_completion(self, job_id: str, poll_interval: float = 0.5) -> JobInfo:
        """
        Wait for job completion.

        Args:
            job_id: Job ID
            poll_interval: Polling interval in seconds

        Returns:
            JobInfo with final status
        """
        # Simulate queue delay
        time.sleep(self.queue_delay)

        # Execute job
        self._execute_job(job_id)

        # Wait for completion
        while True:
            job_info = self.get_status(job_id)
            if job_info.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                return job_info
            time.sleep(poll_interval)

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: Job ID

        Returns:
            True if cancelled successfully
        """
        job_info = self.jobs.get(job_id)
        if job_info and job_info.status == JobStatus.RUNNING:
            job_info.status = JobStatus.CANCELLED
            job_info.end_time = self._get_timestamp()
            self._write_status_file(job_id, job_info)
            return True
        return False

    def _write_job_request(self, request: JobRequest) -> None:
        """Write job request to file"""
        request_file = os.path.join(self.job_dir, f"{request.job_id}_request.json")
        with open(request_file, 'w') as f:
            json.dump(asdict(request), f, indent=2)

    def _write_status_file(self, job_id: str, job_info: JobInfo) -> None:
        """Write job status to file"""
        status_file = os.path.join(self.job_dir, f"{job_id}_status.json")
        with open(status_file, 'w') as f:
            json.dump(asdict(job_info), f, indent=2)

    def _execute_job(self, job_id: str) -> None:
        """Execute job (simulate job execution)"""
        request_file = os.path.join(self.job_dir, f"{job_id}_request.json")

        if not os.path.exists(request_file):
            job_info = self.jobs.get(job_id)
            if job_info:
                job_info.status = JobStatus.FAILED
                job_info.end_time = self._get_timestamp()
                self._write_status_file(job_id, job_info)
            return

        with open(request_file, 'r') as f:
            request = JobRequest(**json.load(f))

        # Create output directories
        os.makedirs(os.path.dirname(request.stdout_path), exist_ok=True)
        os.makedirs(os.path.dirname(request.stderr_path), exist_ok=True)

        # Update job status to running
        job_info = self.jobs[job_id]
        job_info.status = JobStatus.RUNNING
        job_info.start_time = self._get_timestamp()
        self._write_status_file(job_id, job_info)

        # Execute command (simulate by running in subprocess)
        try:
            with open(request.stdout_path, 'w') as stdout_f, open(request.stderr_path, 'w') as stderr_f:
                process = self._run_subprocess(request.command, request.workdir, stdout_f, stderr_f)

                # Simulate runtime
                time.sleep(self.default_runtime)

                # Mark as completed
                job_info.status = JobStatus.COMPLETED
                job_info.end_time = self._get_timestamp()
                job_info.exit_code = process.returncode
                self._write_status_file(job_id, job_info)

        except Exception as e:
            job_info.status = JobStatus.FAILED
            job_info.end_time = self._get_timestamp()
            self._write_status_file(job_id, job_info)

    def _run_subprocess(self, command: str, workdir: str, stdout_f, stderr_f):
        """Run command in subprocess"""
        import subprocess
        return subprocess.Popen(
            command,
            cwd=workdir,
            shell=True,
            stdout=stdout_f,
            stderr=stderr_f
        )

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO8601 string"""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
