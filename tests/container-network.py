#!/usr/bin/env python3
"""Exercise the actual Egg runtime with one port mapped for both protocols."""
import http.client, json, pathlib, socket, struct, subprocess, time
root = pathlib.Path('.ci-server').resolve()
name = 'ryzemp-native-network-ci'
log = open(root / 'network-startup.log', 'w+')
process = subprocess.Popen(['docker','run','--rm','-i','--name',name,'--entrypoint','/bin/bash',
    '-p','127.0.0.1:19132:19132/tcp','-p','127.0.0.1:19132:19132/udp',
    '-v',f'{root}:/home/container','-w','/home/container','ghcr.io/ptero-eggs/yolks:debian',
    './start-ryzemp.sh'], stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True)
def request(method, path, body=None):
    connection = http.client.HTTPConnection('127.0.0.1',19132,timeout=1)
    try:
        connection.request(method,path,body,{'Content-Type':'application/sdp'} if body is not None else {})
        response=connection.getresponse()
        return response.status,response.read()
    finally:
        connection.close()
try:
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise RuntimeError(f'Egg exited before authenticated signaling became ready: {process.returncode}')
        try:
            code,body=request('GET','/v1/join')
            if code==200:
                break
        except (OSError,http.client.HTTPException):
            pass
        time.sleep(.2)
    else:
        raise RuntimeError('Egg never returned a ready HTTP capability response')
    metadata=json.loads(body)
    assert metadata['protocol']==2225 and metadata['version']=='1.26.60',metadata
    assert request('POST','/v1/join/unsigned','v=0\r\n')[0]==401
    ports=json.loads(subprocess.check_output(['docker','inspect',name,'--format','{{json .NetworkSettings.Ports}}'],text=True))
    for protocol in ('tcp','udp'):
        assert ports[f'19132/{protocol}'][0]['HostPort']=='19132',ports
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
        udp.settimeout(3)
        magic=bytes.fromhex('00ffff00fefefefefdfdfdfd12345678')
        udp.sendto(b'\x01'+struct.pack('>q',int(time.time()*1000))+magic+struct.pack('>q',12345),('127.0.0.1',19132))
        pong,peer=udp.recvfrom(4096)
        assert peer[1]==19132 and pong[0]==0x1c
    process.stdin.write('stop\n')
    process.stdin.flush()
    process.wait(timeout=25)
    assert process.returncode==0,process.returncode
finally:
    if process.poll() is None:
        subprocess.run(['docker','stop','--time','10',name],check=False,stdout=subprocess.DEVNULL)
        process.wait(timeout=20)
    log.seek(0)
    output=log.read()
    print(output)
    log.close()
assert 'NetherNet READY:' in output
assert not any(x in output for x in ('Fatal error','Uncaught','CRITICAL','EMERGENCY','NetherNet UNAVAILABLE'))
print('PASS: actual Pterodactyl images, official native runtime and PHAR; same allocation published TCP+UDP, live authenticated HTTP, rejected unsigned offer, real RakNet pong and clean shutdown. Real Wings host and retail client validation remain pending.')
