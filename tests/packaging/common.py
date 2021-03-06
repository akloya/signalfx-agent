from functools import partial as p
from contextlib import contextmanager
import docker
from io import BytesIO
import os
import glob
import random
import subprocess
import tarfile
import threading
import time

from tests.helpers import fake_backend
from tests.helpers.util import get_docker_client, run_container, wait_for
from tests.helpers.assertions import *

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
PACKAGING_DIR = os.path.join(PROJECT_DIR, "packaging")
INSTALLER_PATH = os.path.join(PROJECT_DIR, "deployments/installer/install.sh")
RPM_OUTPUT_DIR = os.path.join(PACKAGING_DIR, "rpm/output/x86_64")
DEB_OUTPUT_DIR = os.path.join(PACKAGING_DIR, "deb/output")
DOCKERFILES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "images"))

INIT_SYSV = "sysv"
INIT_UPSTART = "upstart"
INIT_SYSTEMD = "systemd"

basic_config = """
monitors:
  - type: collectd/signalfx-metadata
  - type: collectd/cpu
  - type: collectd/uptime
"""

def build_base_image(name):
    client = get_docker_client()
    image, logs = client.images.build(
        path=DOCKERFILES_DIR,
        dockerfile=os.path.join(DOCKERFILES_DIR, "Dockerfile.%s" % name),
        rm=True,
        forcerm=True)

    return image.id


def get_agent_logs(container, init_system):
    LOG_COMMAND = {
        INIT_SYSV: "cat /var/log/signalfx-agent.log",
        INIT_UPSTART: "cat /var/log/signalfx-agent.log",
        INIT_SYSTEMD: "journalctl -u signalfx-agent",
    }
    try:
        _, output = container.exec_run(LOG_COMMAND[init_system])
    except docker.errors.APIError as e:
        print("Error getting agent logs: %s" % e)
        return ""
    return output


def get_deb_package_to_test():
    return get_package_to_test(DEB_OUTPUT_DIR, "deb")


def get_rpm_package_to_test():
    return get_package_to_test(RPM_OUTPUT_DIR, "rpm")


def get_package_to_test(output_dir, extension):
    pkgs = glob.glob(os.path.join(output_dir, "*.%s" % extension))
    if not pkgs:
        raise AssertionError("No .%s files found in %s" % (extension, output_dir))

    if len(pkgs) > 1:
        raise AssertionError("More than one .%s file found in %s" % (extension, output_dir))

    return pkgs[0]


# Run an HTTPS proxy inside the container with socat so that our fake backend
# doesn't have to worry about HTTPS.  The cert file must be trusted by the
# container running the agent.
# This is pretty hacky but docker makes it hard to communicate from a container
# back to the host machine (and we don't want to use the host network stack in
# the container due to init systems).  The idea is to bind mount a shared
# folder from the test host to the container that two socat instances use to
# communicate using a file to make the bytes flow between the HTTPS proxy and
# the fake backend.
@contextmanager
def socat_https_proxy(container, target_host, target_port, source_host, bind_addr):
    cert = "/%s.cert" % source_host
    key = "/%s.key" % source_host

    socat_bin = os.path.abspath(os.path.join(os.path.dirname(__file__), "images/socat"))
    stopped = False
    socket = "/tmp/scratch/%s-%s" % (source_host, container.id[:12])

    # Keep the socat instance in the container running across container
    # restarts
    def keep_running_in_container(cont, sock):
        while not stopped:
            try:
                cont.exec_run([
                    "socat",
                    "-v",
                    "OPENSSL-LISTEN:443,cert=%s,key=%s,verify=0,bind=%s,fork" % (cert, key, bind_addr),
                    "UNIX-CONNECT:%s" % sock])
            except docker.errors.APIError as e:
                time.sleep(0.1)


    threading.Thread(target=keep_running_in_container, args=(container,socket)).start()

    proc = subprocess.Popen([
        socat_bin,
        "-v",
        "UNIX-LISTEN:%s,fork" % socket,
        "TCP4:%s:%d" % (target_host, target_port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def read_out(p):
        while True:
            c = p.stdout.read()
            if not c:
                return
            print(c)

    threading.Thread(target=read_out, args=(proc,)).start()

    try:
        yield
    finally:
        stopped = True
        # The socat instance in the container will die with the container
        proc.kill()

# This is more convoluted that it should be but seems to be the simplest way in
# the face of docker-in-docker environments where volume bind mounting is hard.
def copy_file_into_container(path, container, target_path):
    tario = BytesIO()
    tar = tarfile.TarFile(fileobj=tario, mode='w')

    with open(path, 'rb') as f:
        info = tarfile.TarInfo(name=target_path)
        info.size = os.path.getsize(path)

        tar.addfile(info, f)

    tar.close()

    container.put_archive("/", tario.getvalue())
    # Apparently when the above `put_archive` call returns, the file isn't
    # necessarily fully written in the container, so wait a bit to ensure it
    # is.
    time.sleep(2)


@contextmanager
def run_init_system_image(base_image):
    image_id = build_base_image(base_image)
    print("Image ID: %s" % image_id)
    with fake_backend.start() as backend:
        container_options = {
            # Init systems running in the container want permissions
            "privileged": True,
            "volumes": {
                "/sys/fs/cgroup": {"bind": "/sys/fs/cgroup", "mode": "ro"},
                "/tmp/scratch": {"bind": "/tmp/scratch", "mode": "rw"},
            },
            "extra_hosts": {
                # Socat will be running on localhost to forward requests to
                # these hosts to the fake backend
                "ingest.signalfx.com": '127.0.0.1',
                "api.signalfx.com": '127.0.0.2',
            },
        }
        with run_container(image_id, wait_for_ip=False, **container_options) as cont:
            # Proxy the backend calls through a fake HTTPS endpoint so that we
            # don't have to change the default configuration included by the
            # package.  The base_image used should trust the self-signed certs
            # included in the images dir so that the agent doesn't throw TLS
            # verification errors.
            with socat_https_proxy(cont, backend.ingest_host, backend.ingest_port, "ingest.signalfx.com", "127.0.0.1"), \
                 socat_https_proxy(cont, backend.api_host, backend.api_port, "api.signalfx.com", "127.0.0.2"):
                yield [cont, backend]
