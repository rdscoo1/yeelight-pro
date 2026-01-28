#!/usr/bin/env python3
"""Simple testing script for Yeelight Pro Gateway - no HA dependencies."""
import asyncio
import json
import random
from typing import Optional, Dict, Any, List


MSG_SPLIT = b'\r\n'


class SimpleGatewayClient:
    """Simple TCP client for Yeelight Pro Gateway."""
    
    def __init__(self, host: str, port: int = 65443):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._msgs: Dict[Any, asyncio.Future] = {}
        self._message_log: List[Dict] = []
    
    async def connect(self) -> bool:
        """Connect to gateway."""
        try:
            print(f"🔌 Подключение к {self.host}:{self.port}...")
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            print(f"✅ Подключено успешно")
            return True
        except Exception as exc:
            print(f"❌ Ошибка подключения: {exc}")
            return False
    
    async def disconnect(self):
        """Disconnect from gateway."""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            print(f"🔌 Отключено")
    
    async def send(self, method: str, wait_result: bool = True, **kwargs) -> Optional[Dict]:
        """Send command to gateway."""
        if not self.writer:
            print(f"❌ Не подключено к шлюзу")
            return None
        
        # Generate command ID
        if method in ("gateway_get.topology", "device_get.topology"):
            cid = method.replace("_get.", "_post.")
        else:
            cid = random.randint(1_000_000_000, 2_147_483_647)
        
        # Prepare future for response
        fut: Optional[asyncio.Future] = None
        if wait_result:
            fut = asyncio.get_running_loop().create_future()
            self._msgs[cid] = fut
        
        # Build message
        dat = {
            'id': cid,
            'method': method,
            **kwargs,
        }
        
        print(f"\n📤 Отправка: {method}")
        print(f"   Данные: {json.dumps(dat, ensure_ascii=False)}")
        
        try:
            self.writer.write(json.dumps(dat).encode() + MSG_SPLIT)
            await self.writer.drain()
        except Exception as exc:
            print(f"❌ Ошибка отправки: {exc}")
            if cid in self._msgs:
                del self._msgs[cid]
            return None
        
        if not fut:
            return None
        
        try:
            await asyncio.wait_for(fut, timeout=10)
        except asyncio.TimeoutError:
            print(f"⏱️  Таймаут ожидания ответа")
            return None
        finally:
            self._msgs.pop(cid, None)
        
        return fut.result()
    
    async def read_messages(self, duration: int = 5):
        """Read messages for specified duration."""
        print(f"\n👀 Чтение сообщений в течение {duration} секунд...")
        
        buffer = b""
        end_time = asyncio.get_event_loop().time() + duration
        
        while asyncio.get_event_loop().time() < end_time:
            try:
                # Read with timeout
                remaining = end_time - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                
                chunk = await asyncio.wait_for(
                    self.reader.readline(),
                    timeout=min(remaining, 1.0)
                )
                
                if not chunk:
                    print(f"⚠️  Соединение закрыто")
                    break
                
                buffer += chunk
                if buffer.endswith(MSG_SPLIT):
                    msg = buffer[:-len(MSG_SPLIT)]
                    buffer = b""
                    if msg:
                        await self._handle_message(msg)
            
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                print(f"❌ Ошибка чтения: {exc}")
                break
        
        print(f"✅ Чтение завершено")
    
    async def _handle_message(self, msg: bytes):
        """Handle incoming message."""
        try:
            data = json.loads(msg.decode())
            self._message_log.append(data)
            
            method = data.get("method", "unknown")
            cid = method if method in ("gateway_post.topology", "device_post.topology") else data.get("id")
            
            print(f"\n📥 Входящее сообщение:")
            print(f"   Method: {method}")
            print(f"   ID: {cid}")
            
            # Show nodes if present
            nodes = data.get("nodes", [])
            if nodes:
                print(f"   Nodes: {len(nodes)}")
                for node in nodes[:3]:  # Show first 3
                    print(f"     - ID: {node.get('id')}, Type: {node.get('type')}, Name: {node.get('name')}")
                if len(nodes) > 3:
                    print(f"     ... и еще {len(nodes) - 3} узлов")
            
            # Show props if present
            if method in ("gateway_post.prop", "device_post.prop"):
                for node in nodes:
                    print(f"     Device {node.get('id')} props: {node.get('prop', {})}")
            
            # Show events if present
            if method in ("gateway_post.event", "device_post.event"):
                for node in nodes:
                    print(f"     Device {node.get('id')} event: {node.get('event', {})}")
            
            # Resolve future if waiting
            if cid in self._msgs:
                self._msgs[cid].set_result(data)
        
        except Exception as exc:
            print(f"❌ Ошибка обработки сообщения: {exc}")


async def test_gateway(host: str):
    """Test gateway connection and commands."""
    
    print("=" * 80)
    print("🧪 Тестирование Yeelight Pro Gateway")
    print("=" * 80)
    
    client = SimpleGatewayClient(host)
    
    try:
        # Connect
        if not await client.connect():
            return
        
        # Request topology
        print(f"\n🌐 Шаг 1: Запрос топологии")
        print("=" * 80)
        topology = await client.send('gateway_get.topology', wait_result=True)
        
        if topology:
            print(f"\n✅ Топология получена")
            print(f"\n📊 Полная структура:")
            print(json.dumps(topology, indent=2, ensure_ascii=False))
            
            nodes = topology.get('nodes', [])
            print(f"\n📍 Узлов в топологии: {len(nodes)}")
            
            # Show device details
            print(f"\n📱 Устройства:")
            for i, node in enumerate(nodes):
                print(f"\n  [{i}] {node.get('name', 'Unknown')}")
                print(f"      ID: {node.get('id')}")
                print(f"      Type: {node.get('type')}")
                print(f"      PID: {node.get('pid')}")
                print(f"      Model: {node.get('model')}")
                print(f"      Online: {node.get('o', False)}")
                
                # Show some properties
                prop = node.get('prop', {})
                if prop:
                    print(f"      Properties:")
                    for key, value in list(prop.items())[:5]:
                        print(f"        {key}: {value}")
                    if len(prop) > 5:
                        print(f"        ... и еще {len(prop) - 5} свойств")
        else:
            print(f"❌ Не удалось получить топологию")
            return
        
        # Get detailed info for first device
        if nodes:
            first_device_id = nodes[0].get('id')
            print(f"\n🔍 Шаг 2: Детальная информация об устройстве {first_device_id}")
            print("=" * 80)
            
            node_info = await client.send(
                'gateway_get.node',
                params={'id': first_device_id},
                wait_result=True
            )
            
            if node_info:
                print(f"\n✅ Информация получена")
                print(f"\n📊 Полный ответ:")
                print(json.dumps(node_info, indent=2, ensure_ascii=False))
        
        # Test sending a command if there's a controllable device
        light_device = None
        for node in nodes:
            if node.get('type') in ('light', 'ct_bulb', 'color', 'mono'):
                light_device = node
                break
        
        if light_device:
            dev_id = light_device.get('id')
            print(f"\n⚙️  Шаг 3: Тестирование команды")
            print("=" * 80)
            print(f"   Устройство: {light_device.get('name')} (ID: {dev_id})")
            
            # Get current power state
            current_pwr = light_device.get('prop', {}).get('pwr', 0)
            new_pwr = 0 if current_pwr else 1
            
            print(f"   Текущее состояние pwr: {current_pwr}")
            print(f"   Отправка команды pwr={new_pwr}")
            
            result = await client.send(
                'gateway_set.node',
                params={'id': dev_id, 'pwr': new_pwr},
                wait_result=True
            )
            
            if result:
                print(f"\n✅ Команда отправлена")
                print(f"   Ответ: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            # Wait a bit and get updated state
            await asyncio.sleep(1)
            
            updated = await client.send(
                'gateway_get.node',
                params={'id': dev_id},
                wait_result=True
            )
            
            if updated:
                print(f"\n📈 Обновленное состояние:")
                print(json.dumps(updated, indent=2, ensure_ascii=False))
        
        # Monitor messages
        print(f"\n👀 Шаг 4: Мониторинг сообщений (10 секунд)")
        print("=" * 80)
        print("   Попробуйте изменить состояние устройств вручную...")
        
        await client.read_messages(duration=10)
        
        # Summary
        print(f"\n" + "=" * 80)
        print("📊 ИТОГОВАЯ СВОДКА:")
        print("=" * 80)
        print(f"✅ Подключение: Успешно")
        print(f"✅ Топология: {len(nodes)} узлов")
        print(f"✅ Сообщений получено: {len(client._message_log)}")
        
        print(f"\n📝 Типы устройств:")
        device_types: Dict[str, int] = {}
        for node in nodes:
            dtype = node.get('type', 'unknown')
            device_types[dtype] = device_types.get(dtype, 0) + 1
        
        for dtype, count in sorted(device_types.items()):
            print(f"   {dtype}: {count}")
        
        print(f"\n📨 Полученные типы сообщений:")
        message_types: Dict[str, int] = {}
        for msg in client._message_log:
            mtype = msg.get('method', 'response')
            message_types[mtype] = message_types.get(mtype, 0) + 1
        
        for mtype, count in sorted(message_types.items()):
            print(f"   {mtype}: {count}")
        
        print(f"\n💡 Доступные команды:")
        print(f"   - gateway_get.topology - получить топологию")
        print(f"   - gateway_get.node - получить информацию о узле")
        print(f"   - gateway_set.node - отправить команду устройству")
        print(f"   - gateway_get.room - получить информацию о комнате")
        print(f"   - gateway_get.scene - получить список сцен")
        
        print(f"\n📥 Типы входящих сообщений:")
        print(f"   - gateway_post.topology - топология при подключении")
        print(f"   - gateway_post.prop - изменение свойств устройств")
        print(f"   - gateway_post.event - события от устройств")
    
    except Exception as exc:
        print(f"\n❌ Ошибка: {exc}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.disconnect()


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("Простой тестер Yeelight Pro Gateway (без зависимостей HA)")
    print("=" * 80)
    
    try:
        host = input("\n🌐 IP адрес шлюза: ").strip()
        
        if not host:
            print("❌ IP адрес обязателен")
        else:
            asyncio.run(test_gateway(host))
    
    except KeyboardInterrupt:
        print("\n\n👋 Прервано пользователем")
    except EOFError:
        print("\n\n⚠️  Запустите скрипт вручную в терминале:")
        print("  python3 test_gateway_simple.py")
