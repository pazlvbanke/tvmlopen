# tvml

**Работа с датасетами**

tvml имеет доступ к списку экспериментов Barbacane. 
Нужен для того чтобы обновлять датасеты для соответстующих экспериментов или загружать определенную версию датасета чтобы обучить модель. 


tvml.DataWorker - дает доступ к датасетам в S3. 
Объект класса DataWorker требует как минимум один обязательный параметр - коннектор к S3. Так что, если ты не знаешь конкретно к какому эксперименту хочешь подключиться, используй experiments_info(), чтобы посмотреть список доступных экспериментов


experiment = DataWorker(S3)
experiment.experiments_info()

### Установка  
```sh
$ pip install tvml
```

### Создание S3 коннектора
```
import boto3

BUCKET = 'disk-barbacane-test'  # бакет, в котором хранятся датасеты
SRC_S3 = 'dataset_storage'      # папка, в которой хранятся датасеты
S3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY, 
                        aws_secret_access_key=SECRET_KEY, 
                        region_name=REGION)
```

### Инициализация эксперимента
```
from tvml.dsworker import DataWorker

experiment = DataWorker(S3)
experiment.experiments_info()
```
Получаем список имен существующих экспериментов:

*OUTPUT:  { 0: 'Default',
           1: 'tech',
           2: 'imagetype',
           3: 'graphtype',
           4: 'gutenindustries',
           5: 'gutenshifts',
           6: 'gutentag',
           7: 'ssdgraph',
           8: 'trasher'}*

### Скачать обученную модель
Допустим, тебе нужен эксперимент 'tech' - модель, обученная определять технические графики. Чтобы скачать последнюю версию, используй:
```
experiment.pull_model('tech')
```
Можно указать путь, куда сохранять модель

```
experiment.pull_model('tech', '/home/ubuntu/models')
```
