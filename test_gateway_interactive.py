#!/usr/bin/env python3
"""Interactive testing script for Yeelight Pro Gateway."""
import asyncio
import json
import sys
from typing import Optional, Dict, Any

# Add custom_components to path
sys.path.insert(0, '/Users/romankhodukin/Desktop/Programming/HomeAssistant/yeelight-pro')

from custom_components.yeelight_pro.core.gateway import ProGateway
from custom_components.yeelight_pro.core.device import XDevice


class YeelightProTester:
    """Interactive tester for Yeelight Pro Gateway."""
    
    def __init__(self, host: str):
        self.host = host
        self.gateway: Optional[ProGateway] = None
        self.devices: Dict[Any, XDevice] = {}
    
    async def __aenter__(self):
        """Connect to gateway."""
        print(f"\n🔌 Подключение к шлюзу {self.host}:65443...")
        self.gateway = ProGateway(host=self.host, timeout=10, keepalive=30)
        
        try:
            await self.gateway.start()
            print(f"✅ Подключено успешно")
            self.devices = self.gateway.devices
            return self
        except Exception as exc:
            print(f"❌ Ошибка подключения: {exc}")
            raise
    
    async def __aexit__(self, *args):
        """Disconnect from gateway."""
        if self.gateway:
            await self.gateway.stop()
            print(f"\n👋 Отключено от шлюза")
    
    def show_devices(self):
        """Display all discovered devices."""
        print(f"\n📱 Обнаружено устройств: {len(self.devices)}")
        print("=" * 80)
        
        for i, (dev_id, device) in enumerate(self.devices.items()):
            print(f"\n[{i}] {device.name}")
            print(f"    ID: {dev_id}")
            print(f"    Type: {device.type}")
            print(f"    PID: {device.pid}")
            print(f"    Model: {device.model}")
            print(f"    Firmware: {device.firmware_version}")
            print(f"    Online: {device.prop.get('o', False)}")
            
            # Show some properties
            print(f"    Properties ({len(device.prop)} items):")
            for key, value in list(device.prop.items())[:10]:
                print(f"      {key}: {value}")
            if len(device.prop) > 10:
                print(f"      ... и еще {len(device.prop) - 10} свойств")
    
    async def get_topology(self):
        """Request and display topology."""
        print(f"\n🌐 Запрос топологии...")
        result = await self.gateway.topology(wait_result=True)
        
        if result:
            print(f"✅ Топология получена")
            print(f"\n📊 Полный ответ топологии:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            nodes = result.get('nodes', [])
            print(f"\n📍 Узлов в топологии: {len(nodes)}")
            for node in nodes:
                print(f"  - ID: {node.get('id')}, Type: {node.get('type')}, Name: {node.get('name')}")
        else:
            print(f"❌ Не удалось получить топологию")
        
        return result
    
    async def get_node_info(self, node_id: int):
        """Get detailed node information."""
        print(f"\n🔍 Запрос информации о узле {node_id}...")
        result = await self.gateway.get_node(node_id, wait_result=True)
        
        if result:
            print(f"✅ Информация получена")
            print(f"\n📊 Полные данные узла:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Не удалось получить информацию о узле")
        
        return result
    
    async def send_command(self, device_id: int, params: Dict[str, Any]):
        """Send a command to device."""
        print(f"\n⚙️  Отправка команды устройству {device_id}...")
        print(f"    Параметры: {params}")
        
        result = await self.gateway.send(
            'gateway_set.node',
            params={'id': device_id, **params},
            wait_result=True
        )
        
        if result:
            print(f"✅ Команда отправлена")
            print(f"    Ответ: {json.dumps(result, indent=2, ensure_ascii=False)}")
        else:
            print(f"❌ Не удалось отправить команду")
        
        # Wait and get updated state
        await asyncio.sleep(1)
        await self.get_node_info(device_id)
        
        return result
    
    async def monitor_messages(self, duration: int = 30):
        """Monitor incoming messages for a duration."""
        print(f"\n👀 Мониторинг сообщений в течение {duration} секунд...")
        print("    (Попробуйте изменить состояние устройств вручную)")
        print("=" * 80)
        
        # Store original on_message
        original_on_message = self.gateway.on_message
        messages = []
        
        async def capture_message(msg: bytes):
            """Capture and display messages."""
            try:
                data = json.loads(msg.decode())
                messages.append(data)
                
                method = data.get('method', 'unknown')
                nodes = data.get('nodes', [])
                
                print(f"\n📨 Входящее сообщение:")
                print(f"    Method: {method}")
                print(f"    Nodes: {len(nodes)}")
                
                if method in ('gateway_post.prop', 'device_post.prop'):
                    for node in nodes:
                        print(f"    Device {node.get('id')}: {node.get('prop', {})}")
                elif method in ('gateway_post.event', 'device_post.event'):
                    for node in nodes:
                        print(f"    Event from {node.get('id')}: {node.get('event', {})}")
                else:
                    print(f"    Data: {json.dumps(data, indent=2, ensure_ascii=False)[:200]}")
            except Exception as exc:
                print(f"    ⚠️  Ошибка обработки: {exc}")
            
            # Call original handler
            await original_on_message(msg)
        
        # Replace handler
        self.gateway.on_message = capture_message
        
        try:
            await asyncio.sleep(duration)
        finally:
            # Restore original handler
            self.gateway.on_message = original_on_message
        
        print(f"\n✅ Мониторинг завершен, получено сообщений: {len(messages)}")
        return messages


async def main():
    """Main interactive loop."""
    print("=" * 80)
    print("🧪 Интерактивное тестирование Yeelight Pro Gateway")
    print("=" * 80)
    
    # Request gateway host
    host = input("\n🌐 IP адрес шлюза (например, 192.168.1.100): ").strip()
    
    if not host:
        print("❌ IP адрес обязателен")
        return
    
    try:
        async with YeelightProTester(host) as tester:
            # Show discovered devices
            tester.show_devices()
            
            # Get topology
            await tester.get_topology()
            
            # Interactive menu
            while True:
                print("\n" + "=" * 80)
                print("Команды:")
                print("  devices:  Показать все устройства")
                print("  topology: Запросить топологию")
                print("  node <id>: Получить информацию о узле")
                print("  monitor <sec>: Мониторить сообщения N секунд (по умолчанию 30)")
                print("  send <device_id> <key>=<value>: Отправить команду")
                print("    Пример: send 123 pwr=1")
                print("    Пример: send 123 ct=4000")
                print("  q: Выход")
                print("=" * 80)
                
                cmd = input("\n> ").strip().lower()
                
                if cmd == 'q':
                    break
                elif cmd == 'devices':
                    tester.show_devices()
                elif cmd == 'topology':
                    await tester.get_topology()
                elif cmd.startswith('node '):
                    try:
                        node_id = int(cmd.split()[1])
                        await tester.get_node_info(node_id)
                    except (ValueError, IndexError):
                        print("❌ Использование: node <id>")
                elif cmd.startswith('monitor'):
                    try:
                        parts = cmd.split()
                        duration = int(parts[1]) if len(parts) > 1 else 30
                        await tester.monitor_messages(duration)
                    except ValueError:
                        print("❌ Использование: monitor <seconds>")
                elif cmd.startswith('send '):
                    try:
                        parts = cmd.split()
                        device_id = int(parts[1])
                        params = {}
                        for param in parts[2:]:
                            key, value = param.split('=')
                            # Try to convert to int/float if possible
                            try:
                                value = int(value)
                            except ValueError:
                                try:
                                    value = float(value)
                                except ValueError:
                                    pass
                            params[key] = value
                        await tester.send_command(device_id, params)
                    except (ValueError, IndexError) as exc:
                        print(f"❌ Использование: send <device_id> <key>=<value> [<key>=<value> ...]")
                        print(f"   Ошибка: {exc}")
                else:
                    print("❌ Неизвестная команда")
    
    except KeyboardInterrupt:
        print("\n\n👋 Прервано пользователем")
    except Exception as exc:
        print(f"\n❌ Ошибка: {exc}")
        import traceback
        traceback.print_exc()
    
    print("\n👋 Завершено")


if __name__ == "__main__":
    asyncio.run(main())
