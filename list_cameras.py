import subprocess

# function to detect camera index
def list_stream_cameras():
    CAMERA_INDEX = 0

    cmd = ["/usr/bin/v4l2-ctl", "--list-devices"]
    out, err = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    out, err = out.strip(), err.strip()
    for l in [i.split(b"\n\t") for i in out.split(b"\n\n")]:
        if l == [b'']: continue
        index = int(l[1].decode()[-1])
        if index == 0:
            print("Index 0 is skipped because most of the times it belongs to a webcam")
        else:
            print("Found Camera %s as %s" %(l[0].decode(), l[1].decode()))
            CAMERA_INDEX = index

    return CAMERA_INDEX

    