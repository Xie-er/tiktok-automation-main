import socket
import subprocess
import os

def check_ping(ip):
    print(f"--- 正在测试 Ping {ip} ---")
    try:
        # Windows 下的 ping 命令
        result = subprocess.run(['ping', '-n', '2', '-w', '1000', ip], capture_output=True, text=True)
        print(result.stdout)
        return result.returncode == 0
    except Exception as e:
        print(f"Ping 出错: {e}")
        return False

def check_port(ip, port):
    print(f"--- 正在测试端口 {ip}:{port} ---")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        result = sock.connect_ex((ip, port))
        if result == 0:
            print(f"端口 {port} 是 开启 的")
            return True
        else:
            print(f"端口 {port} 是 关闭 的 (错误码: {result})")
            return False
    except Exception as e:
        print(f"端口测试出错: {e}")
        return False
    finally:
        sock.close()

if __name__ == "__main__":
    # 你可以修改这里的 IP
    target_ip = "192.168.0.137"
    adb_port = 5555
    wireless_debug_port = 43255 # 你之前提到的端口
    
    print(f"网络诊断开始...")
    
    ping_ok = check_ping(target_ip)
    
    print("\n--- 端口测试 ---")
    check_port(target_ip, adb_port)
    check_port(target_ip, wireless_debug_port)
    
    print("\n--- 防火墙检查建议 ---")
    print("1. 如果 Ping 不通：请检查手机和电脑是否在【同一个 Wi-Fi】下，且 Wi-Fi 没有开启【AP 隔离】。")
    print("2. 如果 Ping 通但端口关闭：请确认手机上【无线调试】开关已打开，且【端口号】是否正确。")
    print("3. 如果是 Win10/11 防火墙：尝试临时关闭防火墙测试，或者在防火墙设置中允许 adb.exe 通信。")
