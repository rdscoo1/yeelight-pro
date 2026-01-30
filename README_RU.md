# Интеграция Yeelight Pro для Home Assistant

[![CI](https://github.com/rdscoo1/yeelight-pro/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/rdscoo1/yeelight-pro/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/rdscoo1/yeelight-pro)](https://github.com/rdscoo1/yeelight-pro/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[English](README.md) | **Русский**

## Обзор

Yeelight Pro — это пользовательская интеграция для [Home Assistant](https://www.home-assistant.io/), которая подключает ваш **Yeelight Pro Gateway** и все подключенные устройства к экосистеме Home Assistant. Она обеспечивает полный контроль и мониторинг освещения, датчиков, выключателей, климатических устройств и многого другого через локальное TCP-соединение.

> 🧩 Изначально разработано [@hasscc](https://github.com/hasscc), полностью переработано и модернизировано [Романом Ходукиным](https://github.com/rdscoo1) с улучшенной стабильностью, комплексной диагностикой и более 100 автоматизированных тестов.

## Возможности

### Поддержка устройств
- **Освещение** — полный контроль (яркость, цветовая температура, RGB, переходы)
- **Климат** — кондиционеры через Yeelight Pro
- **Шторы** — управление шторами и жалюзи
- **Выключатели** — настенные выключатели, панели, реле
- **Датчики** — движения, открытия, освещенности, температуры, влажности
- **Кнопки** — кнопки сцен и управления панелями
- **Группы** — группы освещения из шлюза

### Мониторинг и диагностика
- **Доступность устройств** на основе статуса онлайн
- **Статус подключения шлюза** как отдельный бинарный датчик
- **Обновление прошивки** — сущность, показывающая доступные обновления
- **Интеграция с шиной событий** для автоматизаций

### Надежность
- **Настраиваемый keepalive** (10-300 секунд)
- **Уведомления о переподключении** с постоянными оповещениями
- **Автоматическое обнаружение устройств** из топологии шлюза
- **Сервис удаления устаревших устройств**

### Поддержка автоматизаций
- Пользовательские сервисы: `send_command`, `mock_incoming_message`, `remove_stale_devices`, `prestage_color_temp`
- Полное отображение состояния сущностей для триггеров и условий
- Публикация в шину событий для продвинутых автоматизаций
- Работает со скриптами, автоматизациями и голосовыми помощниками

## Установка

### Вариант 1 — через HACS (рекомендуется)

1. Откройте **HACS** → **Интеграции** → **⋮** (меню) → **Пользовательские репозитории**
2. Добавьте URL репозитория: `https://github.com/rdscoo1/yeelight-pro.git`
3. Выберите **Integration** в качестве категории
4. Нажмите **Добавить**, затем найдите **Yeelight Pro** и нажмите **Установить**
5. Перезапустите Home Assistant

### Вариант 2 — Ручная установка

1. Скачайте последний релиз с [GitHub Releases](https://github.com/rdscoo1/yeelight-pro/releases)
2. Скопируйте `custom_components/yeelight_pro` в ваш каталог `/config/custom_components/`
3. Перезапустите Home Assistant

## Настройка

1. Перейдите в **Настройки** → **Устройства и службы** → **Добавить интеграцию**
2. Найдите **Yeelight Pro**
3. Введите IP-адрес вашего шлюза (например, `192.168.1.100`)
4. Все подключенные устройства появятся автоматически

### Опции

После настройки вы можете настроить:
- **Интервал keepalive** (10–300 секунд) — как часто пинговать шлюз

## Сущности

Каждое устройство создает сущности в зависимости от своих возможностей:

| Платформа | Пример Entity ID | Описание |
|-----------|------------------|----------|
| `light` | `light.bedroom_ceiling` | Управление светом: питание, яркость, цветовая температура, RGB |
| `climate` | `climate.living_room_ac` | Управление кондиционером: режим, температура, скорость вентилятора |
| `cover` | `cover.bedroom_curtain` | Управление шторами: открыть, закрыть, позиция |
| `switch` | `switch.hallway_relay` | Управление выключателем: вкл/выкл |
| `binary_sensor` | `binary_sensor.door_contact` | Датчик открытия: открыто/закрыто |
| `sensor` | `sensor.living_room_motion` | Датчик движения с атрибутом действия |
| `button` | `button.scene_movie_mode` | Кнопка активации сцены |
| `binary_sensor` | `binary_sensor.gateway_connection` | Статус подключения шлюза |
| `update` | `update.gateway_firmware` | Доступность обновления прошивки |

## Сервисы

### send_command

Отправить сырую команду на шлюз и опционально показать результат в виде постоянного уведомления.

```yaml
service: yeelight_pro.send_command
data:
  host: 192.168.1.100
  method: gateway_get.node
  params:
    id: 0
  throw: true
```

### mock_incoming_message

Имитировать входящее JSON-сообщение от шлюза для тестирования.

```yaml
service: yeelight_pro.mock_incoming_message
data:
  host: 192.168.1.100
  message: >
    {"id": 8218, "method": "gateway_post.event",
     "nodes": [{"params": {}, "value": "motion.false", "id": 301809111, "nt": 2}]}
```

### remove_stale_devices

Удалить устройства, которые больше не присутствуют в топологии шлюза.

```yaml
service: yeelight_pro.remove_stale_devices
data:
  host: 192.168.1.100  # Опционально, удаляет со всех шлюзов, если не указано
  dry_run: true  # Опционально, показывает что будет удалено без фактического удаления
```

### prestage_color_temp

Установить цветовую температуру света, когда он **выключен** (без изменения состояния питания). Это позволяет предварительно настроить температуру света перед включением.

```yaml
service: yeelight_pro.prestage_color_temp
target:
  entity_id: light.bedroom_ceiling
data:
  color_temp_kelvin: 2700  # Теплый белый
```

## Примеры автоматизаций

### 1. Включить свет при обнаружении движения

```yaml
automation:
  - alias: "Движение: Включить свет в коридоре"
    description: "Включить свет при обнаружении движения"
    trigger:
      - platform: state
        entity_id: binary_sensor.hallway_motion
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.hallway_ceiling
        data:
          brightness: 255
```

### 2. Управление кнопкой панели

```yaml
automation:
  - alias: "Панель: Переключить свет в гостиной"
    description: "Переключить свет при одинарном нажатии кнопки"
    trigger:
      - platform: state
        entity_id: sensor.living_room_panel_action
        to: "button1_single"
    action:
      - service: light.toggle
        target:
          entity_id: light.living_room_main
```

### 3. Управление климатом на основе температуры

```yaml
automation:
  - alias: "Климат: Охладить при жаре"
    description: "Включить кондиционер при превышении порога температуры"
    trigger:
      - platform: numeric_state
        entity_id: sensor.living_room_temperature
        above: 26
    action:
      - service: climate.set_hvac_mode
        target:
          entity_id: climate.living_room_ac
        data:
          hvac_mode: cool
      - service: climate.set_temperature
        target:
          entity_id: climate.living_room_ac
        data:
          temperature: 23
```

### 4. Оповещение о переподключении шлюза

```yaml
automation:
  - alias: "Шлюз: Уведомление о переподключении"
    description: "Отправить уведомление при переподключении шлюза"
    trigger:
      - platform: state
        entity_id: binary_sensor.gateway_connection
        from: "off"
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Шлюз Yeelight Pro переподключен"
```

### 5. Управление группой освещения

```yaml
automation:
  - alias: "Группа: Выключить все светильники на ночь"
    description: "Выключить все группы освещения перед сном"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: light.turn_off
        target:
          entity_id: light.yp_group_1_light
```

### 6. Предустановка цветовой температуры перед включением

Используйте сервис `prestage_color_temp` для установки цветовой температуры, когда свет выключен, затем включите его. Это гарантирует, что свет включится с желаемой цветовой температурой сразу.

```yaml
automation:
  - alias: "Свет: Теплый утренний свет"
    description: "Установить теплую цветовую температуру перед включением утреннего света"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      # Сначала установить цветовую температуру, когда свет ВЫКЛЮЧЕН
      - service: yeelight_pro.prestage_color_temp
        target:
          entity_id: light.bedroom_ceiling
        data:
          color_temp_kelvin: 2700  # Теплый белый
      # Затем включить свет
      - service: light.turn_on
        target:
          entity_id: light.bedroom_ceiling
        data:
          brightness: 128
```

### 7. Адаптивное освещение в течение дня

Автоматически меняйте цветовую температуру в зависимости от времени суток:

```yaml
automation:
  - alias: "Свет: Адаптивная температура"
    description: "Изменение цветовой температуры в течение дня"
    trigger:
      - platform: time
        at: "06:00:00"
        id: morning
      - platform: time
        at: "12:00:00"
        id: noon
      - platform: time
        at: "18:00:00"
        id: evening
      - platform: time
        at: "22:00:00"
        id: night
    action:
      - choose:
          - conditions:
              - condition: trigger
                id: morning
            sequence:
              - service: yeelight_pro.prestage_color_temp
                target:
                  entity_id: light.living_room_main
                data:
                  color_temp_kelvin: 4000  # Нейтральный белый
          - conditions:
              - condition: trigger
                id: noon
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.living_room_main
                data:
                  color_temp_kelvin: 5500  # Холодный белый
          - conditions:
              - condition: trigger
                id: evening
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.living_room_main
                data:
                  color_temp_kelvin: 3500  # Теплый нейтральный
          - conditions:
              - condition: trigger
                id: night
            sequence:
              - service: yeelight_pro.prestage_color_temp
                target:
                  entity_id: light.living_room_main
                data:
                  color_temp_kelvin: 2700  # Теплый белый
```

## Устранение неполадок

| Проблема | Причина | Решение |
|----------|---------|---------|
| Интеграция не загружается | Старые или поврежденные файлы | Переустановите через HACS |
| Не удается подключиться к шлюзу | Неверный IP или проблема с сетью | Проверьте IP шлюза и сетевое подключение |
| Устройство показывает недоступно | Устройство офлайн или отключено | Проверьте питание и подключение устройства |
| Сущности не появляются | Устройство не в топологии | Проверьте приложение шлюза и сопряжение устройства |
| Предупреждения об устаревании | Использование старых констант | Обновите до последней версии |

### Включить отладочное логирование

Добавьте в `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.yeelight_pro: debug
    custom_components.yeelight_pro.core: debug
```

Просмотр логов: **Настройки** → **Система** → **Логи** → фильтр по `yeelight_pro`

## Разработка

### Локальная настройка

```bash
git clone https://github.com/rdscoo1/yeelight-pro.git
cd yeelight-pro
python3 -m venv .venv
source .venv/bin/activate  # На Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### Запуск тестов

```bash
pytest              # Быстрый запуск
pytest -vv          # Подробный вывод
pytest --cov        # С отчетом о покрытии
```

### Покрытие тестами

Набор тестов включает **более 100 тестов**, охватывающих:

| Модуль | Покрытие |
|--------|----------|
| `__init__.py` | Настройка, координатор, управление сущностями |
| `core/device.py` | Классы устройств, конвертеры, обновления состояния |
| `core/gateway.py` | TCP-соединение, парсинг сообщений, keepalive |
| `light.py` | Сущность освещения, цветовые режимы, переходы |
| `binary_sensor.py` | Бинарные датчики, подключение шлюза |
| `config_flow.py` | Поток настройки и опций |
| `update.py` | Сущности обновления прошивки |

### CI/CD

Этот репозиторий использует GitHub Actions для:
- **pytest** — автоматизированное тестирование на Python 3.11 и 3.12
- **HACS validation** — проверка совместимости с HACS
- **hassfest** — валидация манифеста Home Assistant

### Создание релиза

1. Обновите `version` в `manifest.json`
2. Закоммитьте и запушьте изменения
3. Создайте тег:
   ```bash
   git tag -a v1.0.0 -m "Release 1.0.0"
   git push --tags
   ```
4. Создайте GitHub Release

## Благодарности

| Роль | Участник |
|------|----------|
| Ведущий разработчик | [Роман Ходукин](https://github.com/rdscoo1) |
| Оригинальная интеграция | [@hasscc](https://github.com/hasscc) |
| Платформа | [Yeelight](https://www.yeelight.com/) |

## Лицензия

Этот проект лицензирован под [MIT License](LICENSE).
