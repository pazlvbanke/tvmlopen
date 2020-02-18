import os
from pathlib import Path
import re


MACOS = True
BUCKET = 'disk-barbacane-test'
SRC_S3 = 'dataset_storage'

class DataWorker:

    def __init__(self, s3_client, path, name, version=None):
        """
            path - полный путь до папки с экспериментом.
            name - имя эксперимента
            в папке path/name папка каждого класса называется
            точно так же как и сам класс
        """
        self.client = s3_client
        self.LOCAL = path
        self.experiment_name = name
        self.src = Path(self.LOCAL) / self.experiment_name
        self.classes = self._set_classnames()
        self.version = version if version else self.new_version_number()
        # self.version = version if version else self.existing_versions()

    def __repr__(self):
        return f"experiment :  {self.experiment_name}\n" \
               f"   version :  {self.version}\n" \
               f"   classes :  {self.classes}\n"

    @staticmethod
    def remove_dstore(src_dir):
        """ Нужно только для макоси """
        if not MACOS: return
        for filename in Path(src_dir).rglob('.DS_Store'):
            print("REMOVE >>>", filename)
            os.remove(filename)

    def _set_classnames(self):
        self.remove_dstore(self.src)
        pattern = re.compile("v\d+")
        classes = [x for x in os.listdir(self.src) if not pattern.match(x) and "dataset" not in x]
        return classes

    def _class_digest(self, class_dir, version=None):
        given_version = self.version if version is None else version
        print("creating v%d digest ..." % given_version)
        dgst_path = self.src/f'v{given_version}'
        os.makedirs(dgst_path, exist_ok=True)

        dgst_name = f"{class_dir.name}.dgst"
        f = open(os.path.join(dgst_path, dgst_name), 'w')

        self.remove_dstore(dgst_path)
        f.writelines([x + '\n' for x in os.listdir(class_dir)])
        return os.path.join(dgst_path, dgst_name)

    @staticmethod
    def _get_all_s3_objects(s3, **base_kwargs):
        continuation_token = None
        while True:
            list_kwargs = dict(MaxKeys=1000, **base_kwargs)
            if continuation_token:
                list_kwargs['ContinuationToken'] = continuation_token
            response = s3.list_objects_v2(**list_kwargs)
            yield from response.get('Contents', [])
            if not response.get('IsTruncated'):  # At the end of the list?
                break
            continuation_token = response.get('NextContinuationToken')

    def new_version_number(self):
        pattern = re.compile("v\d+")
        versions = [int(x.replace('v', '')) for x in os.listdir(self.src) if pattern.match(x)]
        if versions == []: return 1
        return sorted(versions)[-1] + 1

    def existing_versions(self):
        path = Path(SRC_S3)/f'{self.experiment_name}'
        pattern = re.compile(f"v\d+")
        # versions = [x['Key'] for x in S3.list_objects(Bucket=BUCKET,
        #                                               Prefix=str(path))['Contents'] if pattern.match(x['Key'])]
        # return max([int(x.replace('v', '')) for x in self.version]) if versions != [] else 0
        return

    def _compose_dataset(self):
        """ on local !!!! """
        from shutil import copyfile

        for cls in self.classes:
            f_lines = open(f"{self.src}/v{self.version}/{cls}.dgst", 'r').readlines()

            file_names = [self.src/cls/x.strip() for x in f_lines]
            targ_names = [self.src/Path('dataset')/cls/x.strip() for x in f_lines]

            os.makedirs(self.src/'dataset'/cls, exist_ok=True)
            for s, t in zip(file_names, targ_names): copyfile(s, t)

    def compose_dataset_remote(self):
        """ ненужное гавно """
        S3 = self.client
        for cls in self.classes:
            digest_path = Path(SRC_S3)/self.experiment_name/f"v{self.version}/{cls}.dgst"
            print(digest_path)
            obj = S3.get_object(Bucket=BUCKET, Key=str(digest_path))
            list_filenames = obj["Body"].read().decode().split("\n")
            old_image_paths = [Path(SRC_S3)/self.experiment_name/cls/x for x in list_filenames]

            new_prefix = Path(SRC_S3)/self.experiment_name/f"dataset_v{self.version}/{cls}"
            new_image_paths = [new_prefix/x for x in list_filenames]

            already_have = [Path(x['Key']).name for x in \
                            self._get_all_s3_objects(S3, Bucket=BUCKET, Prefix=str(new_prefix))]

            for src, targ in zip(old_image_paths, new_image_paths):
                if src.suffix not in ['.png', '.jpg']: continue
                if targ.name in already_have:
                    print("skip")
                    continue
                copy_source = {"Bucket": BUCKET, "Key": str(src)}
                S3.copy(CopySource=copy_source, Bucket=BUCKET, Key=str(targ))
                print(targ)


    def _compress_dataset(self):
        from shutil import make_archive

        archive_name = f"dataset_v{self.version}"
        make_archive(self.src/archive_name, 'zip', self.src/'dataset')
        return archive_name

    def upload_changes(self, files):
        S3 = self.client
        print("uploading changes to S3 ...")
        for f in files:
            S3.upload_file(f, BUCKET, os.path.join(SRC_S3, f.replace(self.LOCAL+'/', "")))

        request = self._get_all_s3_objects(S3, Bucket=BUCKET, Prefix=os.path.join(SRC_S3, self.experiment_name))
        stored_images = [Path(x['Key']).name for x in request]
        images = [str(x) for x in self.src.glob('**/*') if x.parent.name in self.classes]

        for i, img in enumerate(images):
            s3_key = os.path.join(SRC_S3, img.replace(self.LOCAL+'/', ""))

            if img.split('/')[-1] in stored_images: continue
            S3.upload_file(str(img), BUCKET, s3_key)
            print(f"{i}/{len(images)} upl >> ", Path(img).name)
        print('done !')

    def update(self):
        """
            объект-датасет обновляется всем, что найдет нового в папке
            - создаст новую папку версии со слепком нового датасета,
            - новые картинки зальет в общую папку,
            - слепки отправит на s3
        """
        version = self.new_version_number()
        digest_file_paths = []
        for cls in self.classes:
            digest_file_paths.append(self._class_digest(self.src/cls, version))
        self.upload_changes(files=digest_file_paths)

    def _update_local(self):
        """ переместить в S3 картинки которые поменяли класс """
        print("removing deprecated images from local ...")
        todel_mapping = self.diff_mapping()
        for cls, images in todel_mapping.items():
            if len(images) == 0: continue
            for img in images:
                key = os.path.join(SRC_S3, self.experiment_name, cls, img)
                os.remove(key)
                print("remove from S3 >> ", cls, img)
        print("done!")

    def _version_file_mapping(self):
        _version = self.version

        def read_digest_file(class_name):
            S3 = self.client
            path = os.path.join(SRC_S3, self.experiment_name,
                                f'v{_version}', class_name + '.dgst')
            obj = S3.get_object(Bucket=BUCKET, Key=path)
            digest_data = obj['Body'].read()
            img_names = digest_data.decode().split('\n')
            return img_names
        return {cls: read_digest_file(cls) for cls in self.classes}

    def _s3_file_mapping(self):
        S3 = self.client
        s3_class_mapping = {}
        for classname in self.classes:
            print('collect ', classname)
            class_path = os.path.join(SRC_S3, self.experiment_name, classname)
            response = self._get_all_s3_objects(S3, Bucket=BUCKET, Prefix=class_path)
            responce_contents = filter(lambda a: Path(a).suffix in ['.png', '.jpg'],
                                       [x['Key'] for x in response])
            s3_class_mapping.update({classname: list(responce_contents)})
        return s3_class_mapping

    def _local_file_mapping(self):
        loc_mapping = {}
        for classname in self.classes:
            print('collect ', classname)
            class_path = (Path(self.LOCAL)/f'{self.experiment_name}/{classname}')
            class_contents = class_path.rglob("**/*")
            loc_mapping[classname] = [str(x) for x in class_contents]
        return loc_mapping

    def diff_mapping(self):
        """ что удалить из s3 """

        loc_mapping = self._local_file_mapping()
        version_mapping = self._version_file_mapping()

        del_mapping = {}
        for cls, cls_mapping in loc_mapping.items():
            cls_mapping = [Path(y).name for y in cls_mapping]
            vrs_mapping = [Path(y).name for y in version_mapping[cls]]
            tmp = set(cls_mapping) - set(vrs_mapping)
            del_mapping[cls] = tmp
        return del_mapping

    def compose(self, version):
        """
            Собирает датасет из слепка, по указанному номеру версии
            Сохраняет на локалке
        """
        self._compose_dataset(version)
        self._compress_dataset(version)

    def download(self, version=None, deprecated=True):
        """ downloads given version of dataset from S3

            - version - если не указать версию, то скачается последняя
            ВАЖНО: сейчас последняя версия определяется по той папке
            что лежит на локалке.
            TODO: Переделать узнавание высшей версии на запрос к S3

        """
        # удаляем с локалки все, что не соответствует текущей версии
        S3 = self.client
        self._update_local()

        if not version: version = self.new_version_number() - 1
        request = S3.list_objects(Bucket=BUCKET,
                                  Prefix=os.path.join(SRC_S3, self.experiment_name,
                                                      f'v{version}'))['Contents']
        digest_files_s3 = [x['Key'] for x in request if x['Key'].endswith(".dgst")]

        already_loaded = filter(lambda x: x.suffix in ['.png', '.jpg'],
                                (Path(self.LOCAL) / self.experiment_name).glob('**/*'))

        for key in digest_files_s3:
            # read digest files and get the list of image names
            # which are listed in a given ds-version
            obj = S3.get_object(Bucket=BUCKET, Key=key)
            digest_data = obj['Body'].read()
            img_names = digest_data.decode().split('\n')

            # create directories named of classes
            # listed in a given ds-version
            classname = Path(key).stem
            # classname = classname.replace('.dgst', '')
            class_path = os.path.join(self.LOCAL, self.experiment_name, classname)
            os.makedirs(class_path, exist_ok=True)

            def rm_image(p):
                os.remove(p)
                print("removed deprecated  > ", p.name)

            # remove existing images which are not needed
            # in the given ds-version
            if deprecated:
                [rm_image(x) for x in already_loaded if x.name not in img_names]

            # download images
            img_keys = [Path(SRC_S3)/f"{self.experiment_name}/{classname}/{img}" for img in img_names]
            for key in img_keys:
                if key.suffix not in ['.png', '.jpg']: continue
                targ_name = str(key).replace(SRC_S3, self.LOCAL)

                if key.name in os.listdir(class_path):
                    print('exists! ', targ_name)
                    continue  # if already exist on local
                try:
                    S3.download_file(BUCKET, str(key), targ_name)
                    print("downloaded ", str(key))
                except Exception as e:
                    print(e, key)
                    continue

    def export_model_to_s3(self):
        S3 = self.client
        model_path = self.src/'export.pkl'
        target_model_path = Path(SRC_S3)/self.experiment_name/f'models/v{self.version}/{model_path.name}'
        figures_path = (self.src/'models').rglob('fig*')
        print("Model is uploaded to S3!")

        S3.upload_file(str(model_path), BUCKET, str(target_model_path))
        for fig in figures_path:
            target_fig_path = Path(SRC_S3)/self.experiment_name/f'models/v{self.version}/{fig.name}'
            S3.upload_file(str(fig), BUCKET, str(target_fig_path))
        print("Figures uploaded to S3!")