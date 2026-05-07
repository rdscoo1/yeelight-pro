# Интеграция Yeelight Pro для Home Assistant

[![CI](https://github.com/rdscoo1/yeelight-pro/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/rdscoo1/yeelight-pro/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/rdscoo1/yeelight-pro)](https://github.com/rdscoo1/yeelight-pro/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[English](README.md) | **Русский**

Yeelight Pro — локальная push-интеграция Home Assistant для шлюзов Yeelight Pro и WiFi Panel. Интеграция подключается к устройству по локальному TCP API, читает топологию шлюза, создает сущности Home Assistant для поддерживаемых устройств и обновляет их состояние из push-сообщений шлюза.

Текущая версия интеграции: **1.3.5**.

## Главное

- Локальное TCP-подключение без облачного опроса и без внешних Python-зависимостей.
- UI config flow для типов шлюза **Gateway Pro** и **WiFi Panel**.
- Автоматическое обнаружение устройств, групп, сцен и сущностей шлюза из топологии.
- Переподключение с экспоненциальной задержкой, keepalive-проверки, очистка ожидающих команд и уведомления о переподключении.
- Повтор команд и пассивная проверка состояния для команд включения/выключения.
- Диагностический сенсор шлюза, diagnostics export Home Assistant и сущности обновления прошивки.
- Сервис очистки устаревших устройств, которых больше нет в топологии.
- Тесты расположены в `tests/components/yeelight_pro/`; в наборе более 180 тестов.

## Поддерживаемые платформы

Интеграция подключает следующие платформы Home Assistant:

- `light`
- `switch`
- `binary_sensor`
- `sensor`
- `number`
- `button`
- `cover`
- `climate`
- `update`

## Поддерживаемые устройства и сущности

Сущности создаются на основе топологии шлюза и свойств, которые сообщает устройство.

| Область | Поддерживаемое поведение |
|---------|--------------------------|
| Шлюз | Бинарный сенсор подключения, сущность обновления прошивки, диагностический сенсор |
| Свет | Вкл/выкл, яркость, цветовая температура, RGB, длительность перехода, число delay-off |
| Группы света | Групповые light-сущности с определением возможностей по участникам, когда это возможно |
| Панели и реле | Одна или несколько switch-сущностей, сенсор действий панели, опциональная подсветка как light |
| WiFi Panel | Два реле и сенсор действий |
| Датчики движения и присутствия | Бинарный сенсор движения, события, опциональный сенсор освещенности для поддерживаемых датчиков присутствия |
| Датчики открытия | Бинарный сенсор контакта и события открытия/закрытия |
| Крутилки и сенсорные выключатели | Сенсор действий и события кнопок/крутилки |
| Шторы | Открыть, закрыть, стоп, позиция, текущая позиция, опциональный reverse switch |
| Кондиционеры | HVAC-режим, целевая/текущая температура, режим вентилятора, включение/выключение |
| Сцены | Кнопки сцен из топологии шлюза |

Неподдерживаемые типы устройств игнорируются и записываются в лог.

## Установка

### HACS

1. Откройте **HACS** -> **Integrations** -> **Custom repositories**.
2. Добавьте `https://github.com/rdscoo1/yeelight-pro.git`.
3. Выберите категорию **Integration**.
4. Установите **Yeelight Pro**.
5. Перезапустите Home Assistant.

### Ручная установка

1. Скачайте последний релиз из [GitHub Releases](https://github.com/rdscoo1/yeelight-pro/releases).
2. Скопируйте `custom_components/yeelight_pro` в `/config/custom_components/`.
3. Перезапустите Home Assistant.

## Настройка

### Настройка через UI

1. Откройте **Настройки** -> **Устройства и службы** -> **Добавить интеграцию**.
2. Найдите **Yeelight Pro**.
3. Введите IP-адрес шлюза.
4. Выберите тип шлюза:
   - `Gateway Pro`
   - `Wifi Panel`
5. Перед созданием записи интеграция проверит доступность TCP endpoint.

### Опции

В опциях интеграции можно изменить:

| Опция | Значение по умолчанию | Диапазон / значения |
|-------|------------------------|---------------------|
| Host | Текущий host | Любой hostname или IP, доступный Home Assistant |
| Тип шлюза | `Gateway Pro` | `Gateway Pro`, `Wifi Panel` |
| Port | `65443` | `1`-`65535` |
| Keepalive | `30` секунд | `10`-`300` секунд |
| Transition time | `5.0` секунд | `0.5`-`30.0` секунд |

Изменение опций перезагружает config entry, чтобы TCP-клиент шлюза перезапустился с новыми настройками.

### Настройка через YAML

Рекомендуется настройка через UI. YAML все еще поддерживается для записей шлюза:

```yaml
yeelight_pro:
  gateways:
    - host: 192.168.1.100
      pid: 1
      port: 65443
      keepalive: 30
      transition_time: 5.0
```

`pid: 1` — Gateway Pro, `pid: 2` — WiFi Panel.

## Сервисы

### `yeelight_pro.send_command`

Отправляет сырую команду на шлюз. Результат также публикуется в шину событий Home Assistant как `yeelight_pro.send_command`.

```yaml
service: yeelight_pro.send_command
data:
  host: 192.168.1.100
  method: gateway_get.node
  params:
    id: 0
  throw: true
```

Поля:

| Поле | Обязательное | Описание |
|------|--------------|----------|
| `host` | Да | Host шлюза, на который отправляется команда |
| `method` | Да | Метод Gateway API |
| `params` | Нет | Объект параметров команды |
| `result` | Нет | Опциональная подмена результата для события/уведомления |
| `throw` | Нет | Если true, показать persistent notification с результатом |

### `yeelight_pro.mock_incoming_message`

Передает JSON-сообщение в обработчик сообщений шлюза для отладки.

```yaml
service: yeelight_pro.mock_incoming_message
data:
  host: 192.168.1.100
  message: >
    {"id": 8218, "method": "gateway_post.event",
     "nodes": [{"params": {}, "value": "motion.false", "id": 301809111, "nt": 2}]}
```

Некорректный JSON и JSON не в виде объекта отклоняются с persistent notification.

### `yeelight_pro.remove_stale_devices`

Удаляет записи из device registry для устройств, которых больше нет в топологии шлюза. Сначала используйте `dry_run: true`, чтобы посмотреть, что будет удалено.

```yaml
service: yeelight_pro.remove_stale_devices
data:
  host: 192.168.1.100
  dry_run: true
```

`host` опционален. Если он не указан, проверяются все настроенные шлюзы.

### `light.prestage_color_temp`

Устанавливает цветовую температуру Yeelight Pro light-сущности, не включая свет. Это entity service, зарегистрированный на платформе `light`.

```yaml
service: light.prestage_color_temp
target:
  entity_id: light.bedroom_ceiling
data:
  color_temp_kelvin: 2700
```

## События

События устройств публикуются в шину Home Assistant как `yeelight_pro_event`.

Данные события включают:

- `device_id`
- `device_name`
- `device_type`
- `event_type`
- `params`
- `decoded`
- `gateway_host`

Пример автоматизации:

```yaml
automation:
  - alias: "Yeelight panel action"
    trigger:
      - platform: event
        event_type: yeelight_pro_event
        event_data:
          event_type: panel.click
    action:
      - service: light.toggle
        target:
          entity_id: light.living_room_main
```

## Надежность и диагностика

TCP-клиент шлюза рассчитан на длительную локальную работу:

- Цикл переподключения с экспоненциальной задержкой от 1 до 60 секунд.
- Keepalive-пинги через `gateway_get.node` или `device_get.node`.
- Переподключение после нескольких keepalive-ошибок подряд.
- Переподключение после повторяющихся некорректных JSON-сообщений.
- Лимит буфера чтения, чтобы незавершенные payload не росли бесконечно.
- Повтор большинства write/query команд.
- Кэш топологии с TTL 5 минут.
- Сверка состояния после переподключения.
- Устройства, исчезнувшие из топологии, помечаются недоступными, но не удаляются, чтобы сохранить entity ID.
- Пассивная проверка состояния повторяет power-команды, если шлюз сообщил несовпадающее состояние.

Диагностический сенсор шлюза показывает состояние:

- `OK`
- `Degraded`
- `Poor`
- `Disconnected`
- `No Gateway`

Атрибуты диагностики включают uptime, количество сообщений, успешные/неуспешные команды, повторы, success rate, количество переподключений, keepalive-результаты, последнюю ошибку, transition time и возраст кэша топологии.

Также реализован Home Assistant diagnostics export для config entry; значения host редактируются.

## Примеры автоматизаций

### Включить свет при движении

```yaml
automation:
  - alias: "Motion: hallway light"
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

### Предустановить цветовую температуру перед включением

```yaml
automation:
  - alias: "Light: warm morning start"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: light.prestage_color_temp
        target:
          entity_id: light.bedroom_ceiling
        data:
          color_temp_kelvin: 2700
      - service: light.turn_on
        target:
          entity_id: light.bedroom_ceiling
        data:
          brightness: 128
```

### Предпросмотр очистки устаревших устройств

```yaml
service: yeelight_pro.remove_stale_devices
data:
  dry_run: true
```

## Устранение неполадок

| Проблема | Что проверить |
|----------|---------------|
| Интеграция не добавляется | IP шлюза, порт `65443`, доступность в сети и выбранный тип шлюза |
| Шлюз становится недоступным | Стабильность локальной сети и питание шлюза |
| Сущность устройства недоступна | Устройство исчезло из топологии или сообщает offline |
| Устройство не появилось | Проверьте привязку и топологию в приложении Yeelight Pro, затем перезагрузите интеграцию |
| В registry остались старые устройства | Запустите `yeelight_pro.remove_stale_devices` с `dry_run: true`, затем без dry run |
| Сырая команда ничего не делает | Используйте `yeelight_pro.send_command` с `throw: true` и включите debug-логирование |

### Отладочное логирование

Добавьте в `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.yeelight_pro: debug
    custom_components.yeelight_pro.core: debug
```

Затем откройте **Настройки** -> **Система** -> **Логи** и отфильтруйте по `yeelight_pro`.

## Разработка

### Локальная настройка

```bash
git clone https://github.com/rdscoo1/yeelight-pro.git
cd yeelight-pro
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Тесты

```bash
pytest -q
pytest -q --cov=custom_components/yeelight_pro --cov-report=term-missing
```

Тесты находятся в `tests/components/yeelight_pro/` и используют `pytest-homeassistant-custom-component` для фикстур Home Assistant.

CI запускает:

- HACS validation
- hassfest
- pytest на Python 3.11 и 3.12
- загрузку покрытия в Codecov

### Чеклист релиза

1. Обновите `version` в `custom_components/yeelight_pro/manifest.json`.
2. Обновите release notes/changelog.
3. Создайте commit и tag:

   ```bash
   git tag -a v1.3.5 -m "Release 1.3.5"
   git push --tags
   ```

4. Создайте GitHub Release.

## Благодарности

| Роль | Участник |
|------|----------|
| Ведущий разработчик | [@rdscoo1](https://github.com/rdscoo1) |
| Оригинальная интеграция | [@hasscc](https://github.com/hasscc) |
| Платформа | [Yeelight](https://www.yeelight.com/) |

## Лицензия

Проект распространяется под [MIT License](LICENSE).
