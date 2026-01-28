#!/usr/bin/env python3
"""Manual testing script for Yeelight Pro Gateway - comprehensive device inspection."""
import asyncio
import json
import sys
from typing import Dict, Any

# Add custom_components to path
sys.path.insert(0, '/Users/romankhodukin/Desktop/Programming/HomeAssistant/yeelight-pro')

from custom_components.yeelight_pro.core.gateway import ProGateway


async def test_gateway(host: str):
    """Test Yeelight Pro Gateway and inspect all responses."""
    
    print("=" * 80)
    print("🧪 Тестирование Yeelight Pro Gateway")
    print("=" * 80)
    
    gateway = ProGateway(host=host, timeout=10, keepalive=30)
    
    try:
        # Step 1: Connect to gateway
        print(f"\n🔌 Шаг 1: Подключение к {host}:65443")
        await gateway.start()
        print(f"✅ Подключено успешно")
        print(f"   Gateway device: {gateway.device}")
        
        # Step 2: Get topology
        print(f"\n🌐 Шаг 2: Запрос топологии")
        topology = await gateway.topology(wait_result=True)
        
        if topology:
            print(f"✅ Топология получена")
            print(f"\n📊 Полная структура топологии:")
            print(json.dumps(topology, indent=2, ensure_ascii=False))
            
            nodes = topology.get('nodes', [])
            print(f"\n📍 Узлов в топологии: {len(nodes)}")
        else:
            print(f"❌ Не удалось получить топологию")
            return
        
        # Step 3: Show all discovered devices
        print(f"\n📱 Шаг 3: Обнаруженные устройства ({len(gateway.devices)})")
        print("=" * 80)
        
        device_list = []
        for dev_id, device in gateway.devices.items():
            print(f"\n[{len(device_list)}] {device.name}")
            print(f"    ID: {dev_id}")
            print(f"    Type: {device.type}")
            print(f"    PID: {device.pid}")
            print(f"    Model: {device.model}")
            print(f"    Firmware: {device.firmware_version}")
            print(f"    Online: {device.prop.get('o', False)}")
            print(f"    Gateway: {device.gateway.host if device.gateway else 'None'}")
            
            print(f"\n    📋 Все свойства устройства:")
            for key, value in sorted(device.prop.items()):
                print(f"      {key}: {value}")
            
            device_list.append((dev_id, device))
        
        if not device_list:
            print("\n❌ Устройства не найдены")
            return
        
        # Step 4: Get detailed info for each device
        print(f"\n🔍 Шаг 4: Детальная информация о каждом устройстве")
        print("=" * 80)
        
        for dev_id, device in device_list:
            print(f"\n📊 Устройство: {device.name} (ID: {dev_id})")
            
            node_info = await gateway.get_node(dev_id, wait_result=True)
            
            if node_info:
                print(f"✅ Информация получена")
                print(f"\n   Полный ответ get_node:")
                print(json.dumps(node_info, indent=2, ensure_ascii=False))
            else:
                print(f"⚠️  Не удалось получить информацию")
        
        # Step 5: Test sending commands (if there are controllable devices)
        print(f"\n⚙️  Шаг 5: Тестирование команд")
        print("=" * 80)
        
        # Find a light device to test
        light_device = None
        for dev_id, device in device_list:
            if device.type in ('light', 'ct_bulb', 'color', 'mono'):
                light_device = (dev_id, device)
                break
        
        if light_device:
            dev_id, device = light_device
            print(f"\n💡 Тестирование с устройством: {device.name} (ID: {dev_id})")
            
            # Test 1: Get current state
            print(f"\n   Текущее состояние:")
            print(f"     pwr: {device.prop.get('pwr')}")
            print(f"     bri: {device.prop.get('bri')}")
            print(f"     ct: {device.prop.get('ct')}")
            
            # Test 2: Send a command (toggle power)
            current_pwr = device.prop.get('pwr', 0)
            new_pwr = 0 if current_pwr else 1
            
            print(f"\n   🔧 Отправка команды: pwr={new_pwr}")
            result = await gateway.send(
                'gateway_set.node',
                params={'id': dev_id, 'pwr': new_pwr},
                wait_result=True
            )
            
            if result:
                print(f"   ✅ Команда отправлена")
                print(f"      Ответ: {json.dumps(result, indent=2, ensure_ascii=False)}")
            else:
                print(f"   ❌ Не удалось отправить команду")
            
            # Wait and check updated state
            await asyncio.sleep(2)
            
            updated_info = await gateway.get_node(dev_id, wait_result=True)
            if updated_info:
                print(f"\n   📈 Обновленное состояние:")
                print(json.dumps(updated_info, indent=2, ensure_ascii=False))
        else:
            print(f"\n⚠️  Не найдено устройств для тестирования команд")
        
        # Step 6: Monitor messages for 10 seconds
        print(f"\n👀 Шаг 6: Мониторинг сообщений (10 секунд)")
        print("=" * 80)
        print("   Попробуйте изменить состояние устройств вручную...")
        
        messages = []
        original_on_message = gateway.on_message
        
        async def capture_message(msg: bytes):
            """Capture messages."""
            try:
                data = json.loads(msg.decode())
                messages.append(data)
                
                method = data.get('method', 'unknown')
                print(f"\n   📨 {method}")
                
                if method in ('gateway_post.prop', 'device_post.prop'):
                    nodes = data.get('nodes', [])
                    for node in nodes:
                        print(f"      Device {node.get('id')}: {node.get('prop', {})}")
                elif method in ('gateway_post.event', 'device_post.event'):
                    nodes = data.get('nodes', [])
                    for node in nodes:
                        print(f"      Event from {node.get('id')}: {node.get('event', {})}")
            except Exception:
                pass
            
            await original_on_message(msg)
        
        gateway.on_message = capture_message
        
        try:
            await asyncio.sleep(10)
        finally:
            gateway.on_message = original_on_message
        
        print(f"\n✅ Мониторинг завершен, получено сообщений: {len(messages)}")
        
        if messages:
            print(f"\n📊 Все полученные сообщения:")
            for i, msg in enumerate(messages):
                print(f"\n   [{i}] {msg.get('method', 'unknown')}")
                print(json.dumps(msg, indent=2, ensure_ascii=False)[:500])
        
        # Summary
        print(f"\n" + "=" * 80)
        print("📊 ИТОГОВАЯ СВОДКА:")
        print("=" * 80)
        print(f"✅ Подключение: Успешно")
        print(f"✅ Топология: {len(nodes)} узлов")
        print(f"✅ Устройства: {len(gateway.devices)}")
        print(f"✅ Сообщений получено: {len(messages)}")
        
        print(f"\n💡 Типы устройств:")
        device_types: Dict[str, int] = {}
        for _, device in device_list:
            dtype = device.type or 'unknown'
            device_types[dtype] = device_types.get(dtype, 0) + 1
        
        for dtype, count in sorted(device_types.items()):
            print(f"   {dtype}: {count}")
        
        print(f"\n📝 Доступные методы команд:")
        print(f"   - gateway_get.topology / device_get.topology")
        print(f"   - gateway_get.node / device_get.node")
        print(f"   - gateway_set.node (для отправки команд)")
        print(f"   - gateway_get.room")
        print(f"   - gateway_get.scene")
        
        print(f"\n📨 Типы входящих сообщений:")
        print(f"   - gateway_post.topology / device_post.topology (при подключении)")
        print(f"   - gateway_post.prop / device_post.prop (изменение свойств)")
        print(f"   - gateway_post.event / device_post.event (события)")
        
    except Exception as exc:
        print(f"\n❌ Ошибка: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        print(f"\n🔌 Отключение от шлюза...")
        await gateway.stop()
        print(f"✅ Отключено")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("Этот скрипт тестирует подключение к Yeelight Pro Gateway")
    print("=" * 80)
    
    try:
        host = input("\n🌐 IP адрес шлюза (например, 192.168.1.100): ").strip()
        
        if not host:
            print("❌ IP адрес обязателен")
            sys.exit(1)
        
        asyncio.run(test_gateway(host))
        
    except KeyboardInterrupt:
        print("\n\n👋 Прервано пользователем")
    except EOFError:
        print("\n\n⚠️  Скрипт запущен в неинтерактивном режиме")
        print("Пожалуйста, запустите его вручную в терминале:")
        print("  python3 test_gateway_manual.py")
