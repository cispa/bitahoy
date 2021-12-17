
use std::process::Command;

#[cfg(feature="espeak")]
fn say(output:String) {
    Command::new("espeak").arg(output).spawn().expect("Failed to start espeak");
}

#[cfg(not(feature="espeak"))]
fn say(_output:String) {
}


fn ssh_off() {
    Command::new("service").arg("ssh").arg("disable").spawn().expect("Failed to disable ssh");
    Command::new("service").arg("ssh").arg("stop").spawn().expect("Failed to stop ssh");
}

fn ssh_on() {
    Command::new("service").arg("ssh").arg("enable").spawn().expect("Failed to enable ssh");
    Command::new("service").arg("ssh").arg("start").spawn().expect("Failed to start ssh");
}

use std::io::Read;
use std::io::Write;
use std::fs::{OpenOptions};
use std::net::{Shutdown, TcpListener};
use std::{thread, time};

fn get_wdcode() -> Option<[u8; 16]>{
    let mut result = [0u8; 16];
    let mut file = OpenOptions::new().read(true).open("/sys/firmware/devicetree/base/serial-number").ok()?; ///sys/firmware/devicetree/base/serial-number
    file.read(&mut result).ok()?;
    return Some(result);
}

fn client_worker(stream:std::result::Result<std::net::TcpStream, std::io::Error>) -> Option<()> {
    let mut stream = stream.unwrap();
    stream.write(b"Bitahoy Watchdog debug console\nwdcode: ").ok()?;
    if let Some(wdcode) = get_wdcode() {
        stream.write(&wdcode).ok()?;
    }
    else {
        stream.write(b"<unknown>").ok()?;
    }
    let mut active = true;
    
    while active {
        stream.write(b"\n>").ok()?;
        let mut cmd: [u8; 256] = [0; 256];
        stream.read(&mut cmd).ok()?;
        let out = b"Unknown command: ";
        match &cmd[..] {
            [b'h', b'e', b'l', b'p', b'\n', ..] => {stream.write(b"lol\n").ok()?;}
            [b'e', b'x', b'i', b't', b'\n', ..] => {active = false; stream.write(b"bye\n").ok()?;}
            [b's', b's', b'h', b' ', b'o', b'n', b'\n', ..] => {ssh_on(); stream.write(b"enabled ssh\n").ok()?;}
            [b's', b's', b'h', b' ', b'o', b'f', b'f', b'\n', ..] => {ssh_off(); stream.write(b"disabled ssh\n").ok()?;}
            _ => {stream.write(out).ok()?;stream.write(&mut cmd).ok()?;}
        }
        
        
    }
    stream.shutdown(Shutdown::Both).ok()?;
    return Some(());
}

fn debug_console(){
    let listener = TcpListener::bind("0.0.0.0:9123").unwrap();
    println!("listening started, ready to accept");
    for stream in listener.incoming() {
        thread::spawn(|| {
            client_worker(stream);
        });
    }
}

fn set_led(value: bool) -> Option<()>{
    let mut file = OpenOptions::new().read(true).write(true).open("/sys/class/leds/PWR/brightness").ok()?;
    if value {
        file.write_all(b"255\n").ok()?;
    } else {
        file.write_all(b"0\n").ok()?;
    }
    return Some(())
}

fn led() -> Option<()>{
    let mut file = OpenOptions::new().read(true).write(true).open("/sys/class/leds/PWR/trigger").ok()?;
    file.write_all(b"none\n").ok()?;
    let mut on = true;
    #[allow(while_true)]
    while true {
        set_led(on);
        thread::sleep(time::Duration::from_secs(2));
        on = !on;
    }
    return Some(())
}

fn main() {
    say(String::from("Starting Bitahoy Watchdog..."));
    println!("Hello, world!");
    thread::spawn(|| {
        debug_console();
    });
    thread::spawn(|| {
        led();
    });
    #[allow(while_true)]
    while true {
        say(String::from("Bitahoy watchdog is running"));
        thread::sleep(time::Duration::from_secs(10));
    }
}
