import adbutils
import uiautomator2 as u2

def list_devices():
    adb = adbutils.adb
    devices = adb.device_list()
    if not devices:
        print("No devices found.")
        return
    
    print(f"{'Serial':<20} {'Model':<20} {'Product':<20}")
    print("-" * 60)
    for d in devices:
        try:
            # 获取型号信息
            u2_d = u2.connect(d.serial)
            info = u2_d.info
            model = info.get('productName', 'Unknown')
            # 也可以尝试从 adb 获取更详细的型号
            prop_model = d.shell("getprop ro.product.model").strip()
            print(f"{d.serial:<20} {prop_model:<20} {model:<20}")
        except Exception as e:
            print(f"{d.serial:<20} Error getting info: {e}")

if __name__ == "__main__":
    list_devices()
