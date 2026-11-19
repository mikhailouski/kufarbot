# KufarBot

Telegram-бот для отслеживания **новых** объявлений на [kufar.by](https://www.kufar.by)
и [re.kufar.by](https://re.kufar.by) (недвижимость) в указанных разделах.

Когда в отслеживаемом разделе появляется новое объявление, бот присылает уведомление:
заголовок, цену (BYN + ≈USD), город/район, ссылку и первое фото.

## Возможности

- 📎 **Добавление раздела по ссылке** — пришлите ссылку с любыми фильтрами
  (цена, валюта, марка, регион, сортировка и т.д.)
- 🏠 **Поддержка недвижимости** (re.kufar.by) — аренда и продажа квартир, домов и пр.
- ⏱ **Фоновый мониторинг** — периодический опрос разделов (интервал настраивается)
- 🆕 **Только новые объявления** — при добавлении раздела фиксируется «baseline»,
  существующие объявления не рассылаются; новые определяются по `list_id`,
  без повторов даже после перезапуска
- 📋 **Reply-меню** — кнопки под строкой ввода: список разделов, добавление,
  действия (удалить / пауза / возобновить) без ввода команд
- 🐳 **Docker и Kubernetes** — production-деплой через GitHub Actions, GHCR
  и Kubernetes с автоматическим rollback

## Как работает

1. Вы присылаете боту ссылку на раздел с нужными фильтрами.
2. Бот открывает страницу и извлекает из неё **ровно те параметры поиска**,
   которые использует сам сайт (категория, цена, регион, сортировка и т.п.) —
   из служебного JSON `__NEXT_DATA__`.
3. При подключении раздела бот фиксирует «baseline» — текущую выдачу.
4. Каждые `CHECK_INTERVAL` секунд бот опрашивает раздел через внутренний API kufar
   (сортировка по новизне) и присылает объявления, которых не было в baseline.
5. Отправленные `list_id` сохраняются в JSON-хранилище — повторов нет.

Бот работает через **long polling** Telegram. Состояние (разделы и отправленные
`list_id`) хранится в файле `data/bot_state.json`; отдельная база данных не нужна.

## Взаимодействие с ботом

### Первые шаги

1. Найдите своего бота в Telegram и отправьте `/start` — появится приветствие
   и **меню с кнопками** под строкой ввода:

   ```
   [ 📋 Мои разделы ]  [ ➕ Добавить раздел ]
   [ ℹ️ Помощь ]
   ```

### Добавить раздел на отслеживание

**Способ 1 — через кнопки:**
1. Нажмите `➕ Добавить раздел`.
2. Пришлите ссылку на раздел kufar.by или re.kufar.by с нужными фильтрами, например:
   ```
   https://www.kufar.by/l/fotoapparaty/ft~fujifilm?prc=r:100000,100000000000&sort=lst.d
   https://re.kufar.by/l/grodno/snyat/kvartiru?cur=USD&prc=r:200,350&size=30&sort=lst.d
   ```
3. Бот подтвердит добавление и сразу зафиксирует baseline — в чат попадут только
   объявления, появившиеся **после** подключения.

**Способ 2 — командой:** `/watch <ссылка>` — то же самое одной командой.

**Как получить ссылку:** откройте kufar.by, выберите раздел, задайте фильтры
(цена, регион, марка и т.п.) и просто скопируйте адрес из строки браузера.

### Управление разделами (кнопки)

1. Нажмите `📋 Мои разделы` — бот покажет список отслеживаемых разделов кнопками:

   ```
   [ #1 fotoapparaty ]
   [ #2 ⏸ kvartiru ]      ← пометка ⏸ = на паузе
   [ ◀️ Отмена ]
   ```

2. Нажмите на нужный раздел — появится карточка (статус, фильтры, ссылка)
   и кнопки действий:

   ```
   [ 🗑 Удалить #1 ]
   [ ⏸ Пауза #1 ]         ← или [ ▶️ Возобновить #1 ], если на паузе
   [ ◀️ Отмена ]
   ```

3. Действие применяется сразу:
   - **🗑 Удалить** — раздел убирается из отслеживания, бот вернётся к списку;
   - **⏸ Пауза** — раздел временно не опрашивается;
     **▶️ Возобновить** — опрос снова активен;
   - **◀️ Отмена** — возврат в главное меню на любом шаге.

### Команды (дублируют кнопки)

| Команда | Описание |
|---|---|
| `/start` | приветствие, справка и главное меню |
| `/watch <ссылка>` | добавить раздел по ссылке |
| `/list` | текстовый список отслеживаемых разделов |
| `/pause <номер>` | пауза / возобновление раздела |
| `/un <номер>` | удалить раздел |

## Уведомление о новом объявлении

```
📩 Сдам 2-х комнатную квартиру на длительный срок
💵 950 р.  (≈310 USD)
📍 Гродненская область, Гродно
🔗 Открыть объявление
```

К сообщению прикладывается первое фото объявления.

## Получение токена и user id

1. **BOT_TOKEN** — создайте бота у [@BotFather](https://t.me/BotFather)
   (команда `/newbot`) и скопируйте токен.
2. **ADMIN_USER_ID** — напишите [@userinfobot](https://t.me/userinfobot),
   он пришлёт ваш Telegram user id.

## Настройка переменных

| Переменная | Описание | По умолчанию |
|---|---|---|
| `BOT_TOKEN` | токен бота от @BotFather | — |
| `ADMIN_USER_ID` | Telegram user id владельца — только он управляет ботом и получает уведомления | — |
| `CHECK_INTERVAL` | интервал опроса разделов, сек | 60 (в Kubernetes — 300) |
| `CHECK_SIZE` | сколько объявлений брать за один опрос | 50 |
| `MAX_SEND_PER_CHECK` | максимум уведомлений за один цикл | 15 |

Локально переменные читаются из `.env` (см. `.env.example`).

В Kubernetes переменные приходят из двух источников:
- Secret `kufarbot-secret` — `BOT_TOKEN`, `ADMIN_USER_ID`;
- ConfigMap `kufarbot-config` — `CHECK_INTERVAL=300`, `CHECK_SIZE=50`,
  `MAX_SEND_PER_CHECK=15`.

## Локальный запуск

### Вариант 1 — Python venv

**Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполните BOT_TOKEN и ADMIN_USER_ID
python main.py
```

**Windows / PowerShell:**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # заполните BOT_TOKEN и ADMIN_USER_ID
python main.py
```

### Вариант 2 — Docker Compose

`compose.yaml` предназначен **только для локального запуска**; production
работает в Kubernetes.

```bash
cp .env.example .env   # заполните BOT_TOKEN и ADMIN_USER_ID
docker compose up -d --build
docker compose logs -f kufarbot
docker compose down
```

Состояние бота сохраняется в локальном каталоге `./data`.

### Запуск Docker-образа вручную

```bash
docker build -t kufarbot .
docker run --rm \
  --env-file .env \
  -v "$PWD/data:/app/data" \
  kufarbot
```

## Production: GitHub Actions + Kubernetes

### Как устроен деплой

```
push в main
  → GitHub Actions
      → job test: unit-тесты
      → job build-and-push: сборка Docker-образа и публикация в GHCR
  → job deploy на self-hosted runner
      → kubectl set image deployment/kufarbot ...:sha-<commit>
      → kubectl rollout status (180 секунд)
      → при ошибке: kubectl rollout undo и сбор логов
```

Образы публикуются в `ghcr.io/mikhailouski/kufarbot` с тегами:
- `latest` — последняя сборка из `main`;
- `main` — имя ветки;
- `sha-<полный commit SHA>` — точная версия, которую ставит CI.

Pipeline описан в `.github/workflows/pipeline.yaml`. Он запускается при push
в `main` и вручную через `workflow_dispatch`.

### Файлы Kubernetes

| Файл | Назначение |
|---|---|
| `k8s-deployment.yaml` | Deployment `kufarbot` в namespace `lab`: 1 реплика, стратегия `Recreate`, health probes, `hostPath` для данных |
| `k8s-configmap.yaml` | ConfigMap `kufarbot-config` с настройками мониторинга |
| Secret `kufarbot-secret` | создаётся вручную, в git не хранится; содержит `BOT_TOKEN` и `ADMIN_USER_ID` |

### Требования к self-hosted runner

Runner должен иметь labels `self-hosted`, `linux`, `x64`, `kufarbot`, а также:

- установленный `kubectl`;
- доступ к kubeconfig в `/etc/kufarbot-deployer/config`
  (путь задаётся в `KUBECONFIG` внутри pipeline);
- права на namespace `lab`: получать и изменять Deployment, смотреть Pods и логи.

### Первичная настройка кластера

```bash
# 1. Namespace
kubectl create namespace lab

# 2. Секрет с токеном бота и Telegram user id
kubectl -n lab create secret generic kufarbot-secret \
  --from-literal=BOT_TOKEN='<токен от BotFather>' \
  --from-literal=ADMIN_USER_ID='<ваш Telegram user id>'

# 3. Каталог для состояния бота на ноде
sudo mkdir -p /opt/kufarbot/data

# 4. ConfigMap и Deployment
kubectl apply -f k8s-configmap.yaml
kubectl apply -f k8s-deployment.yaml

# 5. Проверка
kubectl -n lab rollout status deployment/kufarbot --timeout=180s
kubectl -n lab get pods -l app=kufarbot -o wide
```

Важно: `k8s-deployment.yaml` использует `hostPath` `/opt/kufarbot/data`.
Каталог должен существовать **на той ноде**, куда попадёт Pod. Для
многонодового кластера вместо `hostPath` лучше использовать PVC.

Если пакет GHCR приватный, создайте pull-секрет и добавьте его в Deployment:

```bash
kubectl -n lab create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username='<github-username>' \
  --docker-password='<personal access token>'
```

```yaml
spec:
  template:
    spec:
      imagePullSecrets:
        - name: ghcr-pull
```

### Автоматический деплой и rollback

После push в `main` CI сам собирает образ и обновляет Deployment.
Если `kubectl rollout status` не завершился за 180 секунд, pipeline:

1. выводит список Pods и последние 50 строк логов;
2. выполняет `kubectl rollout undo deployment/kufarbot`;
3. ждёт завершения rollback и завершает job с ошибкой.

При первом деплое откатываться некуда — в этом случае смотрите логи Pod.

> Повторный `kubectl apply -f k8s-deployment.yaml` сбросит образ на `:latest`,
> потому что CI меняет его через `kubectl set image`. Не применяйте манифест
> без необходимости.

### Эксплуатация

```bash
# Статус
kubectl -n lab get deployment kufarbot -o wide
kubectl -n lab get pods -l app=kufarbot -o wide

# Логи
kubectl -n lab logs -l app=kufarbot --all-containers=true --tail=100 -f

# Перезапуск
kubectl -n lab rollout restart deployment/kufarbot
kubectl -n lab rollout status deployment/kufarbot

# Откат на предыдущую ревизию
kubectl -n lab rollout undo deployment/kufarbot

# История ревизий
kubectl -n lab rollout history deployment/kufarbot
```

### Состояние бота

В Kubernetes файл состояния лежит на ноде:

```
/opt/kufarbot/data/bot_state.json
```

Он смонтирован в контейнер как `/app/data/bot_state.json`.

- Бот должен работать **в одной реплике**: Telegram long polling не допускает
  несколько одновременных polling-подключений, а JSON-хранилище не рассчитано
  на конкурентную запись.
- Для бэкапа достаточно скопировать `bot_state.json` с ноды.
- При переносе Pod на другую ноду без общего volume состояние будет потеряно.

### Health checks

Внутри контейнера на порту `8080` работают два HTTP-эндпоинта:

| Эндпоинт | Что проверяет |
|---|---|
| `GET /health/live` | процесс жив и фоновая задача мониторинга не завершилась |
| `GET /health/ready` | Telegram polling запущен и задача мониторинга активна |

`k8s-deployment.yaml` использует их в `livenessProbe` и `readinessProbe`.
Отдельный Service/Ingress для health-порта не создаётся — Kubernetes
обращается к Pod напрямую. Для ручной проверки:

```bash
kubectl -n lab port-forward deployment/kufarbot 8080:8080

curl -i http://127.0.0.1:8080/health/live
curl -i http://127.0.0.1:8080/health/ready
```

## Структура проекта

```
.github/
  workflows/
    pipeline.yaml      # CI/CD: тесты, сборка образа, деплой в Kubernetes
Dockerfile             # образ для production и локального запуска
.dockerignore
compose.yaml           # только локальный запуск через Docker Compose
.env.example           # шаблон переменных окружения

main.py                # точка входа: Telegram polling, мониторинг, health server
config.py              # чтение .env
storage.py             # JSON-хранилище: разделы + отправленные list_id

bot/
  handlers.py          # команды (/start, /watch, /list, /un, /pause)
  buttons.py           # обработчики reply-кнопок (FSM: меню, действия, добавление)
  keyboards.py         # reply-клавиатуры и тексты кнопок
  menu_flow.py         # «чистый чат»: удаление нажатий и замена меню-сообщений
  context.py           # BotContext — общие зависимости
  watch_service.py     # общая логика добавления раздела по ссылке
  notifier.py          # форматирование и отправка уведомлений

kufar/
  client.py            # запросы к внутреннему API kufar
  urlcast.py           # декодер ссылок kufar/re.kufar => параметры API
  models.py            # модель объявления

tests/
  test_core.py         # юнит-тесты

k8s-configmap.yaml     # ConfigMap с настройками мониторинга
k8s-deployment.yaml    # Deployment, probes, volume для состояния

data/
  bot_state.json       # состояние бота (создаётся автоматически, не в git)
```

## Тесты

```bash
python -m unittest discover -s tests -v
```

Тесты не обращаются к сети. В GitHub Actions они запускаются job-ом `test`
перед сборкой образа; при падении тестов деплой не выполняется.

## Поддерживаемые площадки

- **kufar.by** — все категории (фототехника, электроника, одежда и т.д.)
- **re.kufar.by** — недвижимость (аренда и продажа). Пример ссылки — аренда
  квартир в Гродно за $200–350 по новизне:

  ```
  /watch https://re.kufar.by/l/grodno/snyat/kvartiru?cur=USD&prc=r%3A200%2C350&size=30&sort=lst.d
  ```

Обе площадки обрабатываются одинаково: параметры поиска извлекаются из
`__NEXT_DATA__` страницы и передаются в единый API поиска.

## Примечание по API

Проект использует неофициальный JSON API, которым пользуется сам сайт
(`cre-api.kufar.by/ads-search/v1/.../rendered-paginated`). Эндпоинт может меняться.
Соблюдайте умеренный интервал опроса (`CHECK_INTERVAL`), чтобы не создавать
нагрузку на сайт.

## Troubleshooting

**`TelegramConflictError` / бот не отвечает**

У бота может быть активен webhook или запущен второй экземпляр. Бот при старте
сам удаляет webhook, но второй polling-процесс (например, локальный и в
Kubernetes одновременно) нужно остановить.

**`/health/ready` возвращает 503**

Polling ещё не запустился или фоновая задача мониторинга завершилась.
Проверьте логи:

```bash
kubectl -n lab logs -l app=kufarbot --tail=100
```

**Pod не запускается**

Проверьте:

```bash
kubectl -n lab describe pod -l app=kufarbot
kubectl -n lab logs -l app=kufarbot --tail=100
```

Частые причины: нет Secret `kufarbot-secret`, неверный `BOT_TOKEN`,
отсутствует каталог `/opt/kufarbot/data` на ноде, нет доступа к образу GHCR.

**После перезапуска пропали разделы**

Проверьте, что каталог `/opt/kufarbot/data` смонтирован и сохранился,
и что Pod не переехал на другую ноду без общего volume.

**После `kubectl apply` откатилась версия образа**

Манифест содержит `:latest`. CI ставит `:sha-<commit>` через `kubectl set image`.
Повторное применение манифеста возвращает `:latest`; после этого дождитесь
следующего деплоя или вручную выставьте нужный тег через `kubectl set image`.
