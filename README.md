# fortunate-button

### RPI instructions

What to do when starting from a fresh raspberry pi lite install:

On the machine you're sshing from:
- Reset ssh keys so you can ssh in: `ssh-keygen -R <HOST>`
- Then ssh in

On the raspberry pi:
- `sudo apt update`
- `sudo apt upgrade`
- `sudo apt install vim git pip`
- [Set up GitHub ssh keys](https://gist.github.com/xirixiz/b6b0c6f4917ce17a90e00f9b60566278)
- Clone this repo
- cd into `fortunate-button`
- `python -m venv env` then install the missing thing
- `python -m venv env`
- `source env/bin/activate`
- `pip install --upgrade bleak Pillow RPi.GPIO gpiozero` (or maybe can use `python -m pip install -r requirements.txt`?)
- `sudo apt-get install libopenjp2-7`
- `sudo pip3 install Pillow --break-system-packages` <- needed for running script with root
- [Start script on launch](https://learn.sparkfun.com/tutorials/how-to-run-a-raspberry-pi-program-on-startup#method-1-rclocal)
  - `sudo vim /etc/rc.local`
  - add:
    ```
    sudo bash -c 'source /home/vrk/fortunate-button/env/bin/activate > /home/vrk/blink1.log 2>&1' &
    sudo python3 /home/vrk/fortunate-button/fortune-pi.py &
    ```

### Viewing logs of background process

1. get the process id: `sudo ps -ax | grep python`
2. `sudo strace -p <PID> -e write`

