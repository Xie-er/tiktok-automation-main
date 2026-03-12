import uiautomator2 as u2
import time
import random

def force_test():
    print("Connecting to device...")
    d = u2.connect() # 默认连接
    print(f"Connected to: {d.info.get('serial')}")

    # ID 定义
    ID_OPEN = "com.ss.android.ugc.aweme:id/en1"
    ID_INPUT = "com.ss.android.ugc.aweme:id/el7"
    ID_SEND = "com.ss.android.ugc.aweme:id/eqf"
    
    TEXTS = ["太可爱了！", "真有意思", "赞一个"]

    print(f"\n--- STEP 1: Click OPEN ({ID_OPEN}) ---")
    if d(resourceId=ID_OPEN).exists(timeout=5):
        d(resourceId=ID_OPEN).click()
        print("Success: Clicked en1")
    else:
        print("Error: en1 not found")
        return

    time.sleep(3)

    print(f"\n--- STEP 2: Click INPUT ({ID_INPUT}) ---")
    if d(resourceId=ID_INPUT).exists(timeout=5):
        d(resourceId=ID_INPUT).click()
        print("Success: Clicked el7")
    else:
        print("Error: el7 not found")
        return

    time.sleep(2)

    print(f"\n--- STEP 3: Set TEXT ---")
    text = random.choice(TEXTS)
    d(resourceId=ID_INPUT).set_text(text)
    print(f"Success: Set text to '{text}'")

    time.sleep(2)

    print(f"\n--- STEP 4: Click SEND ({ID_SEND}) ---")
    if d(resourceId=ID_SEND).exists(timeout=5):
        d(resourceId=ID_SEND).click()
        print("Success: Clicked eqf")
    else:
        print("Error: eqf not found")
        return

    print("\nWorkflow Finished!")

if __name__ == "__main__":
    force_test()
