import os
import numpy as np
import supervisely_lib as sly
from supervisely_lib.imaging.image import write
from supervisely_lib.io.fs import mkdir, get_file_name, get_file_ext, silent_remove
from supervisely_lib.io.json import dump_json_file
from supervisely_lib.geometry.bitmap import Bitmap
from supervisely_lib.geometry.polygon import Polygon
from PIL import Image

my_app = sly.AppService()

TEAM_ID = int(os.environ['context.teamId'])
WORKSPACE_ID = int(os.environ['context.workspaceId'])
PROJECT_ID = int(os.environ['modal.state.slyProjectId'])
RESULT_DIR_NAME = 'cityscapes_format'
images_dir_name = 'leftImg8bit'
annotations_dir_name = 'gtFine'
default_dir_train = 'train'
default_dir_val = 'val'
default_dir_test = 'test'
cityscapes_images_suffix = '_leftImg8bit'
cityscapes_polygons_suffix = '_gtFine_polygons.json'
cityscapes_color_suffix = '_gtFine_color.png'
cityscapes_labels_suffix = '_gtFine_labelIds.png'
possible_geometries = [Bitmap, Polygon]
possible_tags = ['train', 'val', 'test']
splitter_coef = 3 / 5
if splitter_coef > 1 or splitter_coef < 0:
    raise ValueError('train_to_val_test_coef should be between 0 and 1, your data is {}'.format(splitter_coef))


def from_ann_to_cityscapes_mask(ann, name2id, app_logger, train_val_flag):
    mask_color = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
    mask_label = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
    poly_json = {'imgHeight': ann.img_size[0], 'imgWidth': ann.img_size[1], 'objects': []}

    for label in ann.labels:
        if type(label.geometry) not in possible_geometries:
            continue
        if train_val_flag:
            label.geometry.draw(mask_color, label.obj_class.color)
        label.geometry.draw(mask_label, name2id[label.obj_class.name])
        if type(label.geometry) == Bitmap:
            curr_cnt = label.geometry.to_contours()
            if len(curr_cnt) == 0:
                continue
            elif len(curr_cnt) == 1:
                poly_for_contours = curr_cnt[0]
            else:
                for poly in curr_cnt:
                    cur_contours = poly.exterior_np.tolist()
                    if len(poly.interior) > 0 and label.obj_class.name != 'out of roi':
                        app_logger.info(
                            'Labeled objects must never have holes in cityscapes format, existing holes will be sketched')
                    cityscapes_contours = list(map(lambda cnt: cnt[::-1], cur_contours))
                    poly_json['objects'].append({'label': label.obj_class.name, 'polygon': cityscapes_contours})
                continue
        else:
            poly_for_contours = label.geometry

        if len(poly_for_contours.interior) > 0 and label.obj_class.name != 'out of roi':
            app_logger.info(
                'Labeled objects must never have holes in cityscapes format, existing holes will be sketched')

        contours = poly_for_contours.exterior_np.tolist()

        if label.obj_class.name == 'out of roi':
            for curr_interior in poly_for_contours.interior_np:
                contours.append(poly_for_contours.exterior_np.tolist()[0])
                contours.extend(curr_interior.tolist())
                contours.append(curr_interior.tolist()[0])

        cityscapes_contours = list(map(lambda cnt: cnt[::-1], contours))
        poly_json['objects'].append({'label': label.obj_class.name, 'polygon': cityscapes_contours})

    return mask_color, mask_label, poly_json


def image_ext_to_png(im_path):
    if get_file_ext(im_path) != '.png':
        im = Image.open(im_path).convert('RGB')
        im.save(im_path[:-1 * len(get_file_ext(im_path))] + '.png')
        silent_remove(im_path)


def get_tags_splitter(anns):
    anns_without_possible_tags = 0
    for ann in anns:
        ann_tags = [tag.name for tag in ann.img_tags]
        separator_tags = list(set(ann_tags) & set(possible_tags))
        if len(separator_tags) == 0:
            anns_without_possible_tags += 1
    train_tags_cnt = round(anns_without_possible_tags * splitter_coef)
    val_tags_cnt = round((anns_without_possible_tags - train_tags_cnt) / 2)
    test_tags_cnt = anns_without_possible_tags - train_tags_cnt - val_tags_cnt
    return {'train': train_tags_cnt, 'val': val_tags_cnt, 'test': test_tags_cnt}


@my_app.callback("from_sl_to_cityscapes")
@sly.timeit
def from_sl_to_cityscapes(api: sly.Api, task_id, context, state, app_logger):
    def get_image_and_ann():
        mkdir(image_dir_path)
        mkdir(ann_dir)
        image_path = os.path.join(image_dir_path, image_name)
        api.image.download_path(image_id, image_path)
        image_ext_to_png(image_path)

        mask_color, mask_label, poly_json = from_ann_to_cityscapes_mask(ann, name2id, app_logger, train_val_flag)
        # dump_json_file(poly_json,
        #                os.path.join(ann_dir, get_file_name(base_image_name) + cityscapes_polygons_suffix))
        # write(
        #     os.path.join(ann_dir,
        #                  get_file_name(base_image_name) + cityscapes_color_suffix), mask_color)
        # write(
        #     os.path.join(ann_dir,
        #                  get_file_name(base_image_name) + cityscapes_labels_suffix), mask_label)

        dump_json_file(
            poly_json, os.path.join(ann_dir,
                                    get_file_name(base_image_name).replace('_leftImg8bit', '') +
                                    cityscapes_polygons_suffix)
        )
        write(
            os.path.join(ann_dir, get_file_name(base_image_name).replace('_leftImg8bit', '') + cityscapes_color_suffix),
            mask_color)
        write(
            os.path.join(ann_dir,
                         get_file_name(base_image_name).replace('_leftImg8bit', '') + cityscapes_labels_suffix),
            mask_label)

    project_name = api.project.get_info_by_id(PROJECT_ID).name
    ARCHIVE_NAME = '{}_{}_Cityscapes.tar.gz'.format(PROJECT_ID, project_name)
    meta_json = api.project.get_meta(PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)
    has_bitmap_poly_shapes = False
    for obj_class in meta.obj_classes:
        if obj_class.geometry_type not in possible_geometries:
            app_logger.warn(
                f'Cityscapes format supports only bitmap and polygon classes, {obj_class.geometry_type} will be skipped')
        else:
            has_bitmap_poly_shapes = True

    if has_bitmap_poly_shapes is False:
        raise Exception('Input project does not contain bitmap or polygon classes')
        my_app.stop()

    RESULT_ARCHIVE = os.path.join(my_app.data_dir, ARCHIVE_NAME)
    RESULT_DIR = os.path.join(my_app.data_dir, RESULT_DIR_NAME)
    result_images_train = os.path.join(RESULT_DIR, images_dir_name, default_dir_train)
    result_images_val = os.path.join(RESULT_DIR, images_dir_name, default_dir_val)
    result_images_test = os.path.join(RESULT_DIR, images_dir_name, default_dir_test)
    result_anns_train = os.path.join(RESULT_DIR, annotations_dir_name, default_dir_train)
    result_anns_val = os.path.join(RESULT_DIR, annotations_dir_name, default_dir_val)
    result_anns_test = os.path.join(RESULT_DIR, annotations_dir_name, default_dir_test)
    sly.fs.mkdir(RESULT_DIR)
    app_logger.info("Cityscapes Dataset folder has been created")

    class_to_id = []
    name2id = {}
    for idx, obj_class in enumerate(meta.obj_classes):
        if obj_class.geometry_type not in possible_geometries:
            continue
        curr_class = {}
        curr_class['name'] = obj_class.name
        curr_class['id'] = idx + 1
        curr_class['color'] = obj_class.color
        class_to_id.append(curr_class)
        name2id[obj_class.name] = (idx + 1, idx + 1, idx + 1)

    dump_json_file(class_to_id, os.path.join(RESULT_DIR, 'class_to_id.json'))
    app_logger.info("Writing classes with colors to class_to_id.json file")

    datasets = api.dataset.get_list(PROJECT_ID)
    for dataset in datasets:
        images_dir_path_train = os.path.join(result_images_train, dataset.name)
        images_dir_path_val = os.path.join(result_images_val, dataset.name)
        images_dir_path_test = os.path.join(result_images_test, dataset.name)
        anns_dir_path_train = os.path.join(result_anns_train, dataset.name)
        anns_dir_path_val = os.path.join(result_anns_val, dataset.name)
        anns_dir_path_test = os.path.join(result_anns_test, dataset.name)

        images = api.image.get_list(dataset.id)
        progress = sly.Progress('Convert images and anns from dataset {}'.format(dataset.name), len(images), app_logger)
        if len(images) < 3:
            app_logger.warn(
                'Number of images in {} dataset is less then 3, val and train directories for this dataset will not be created'.format(
                    dataset.name))

        image_ids = [image_info.id for image_info in images]
        base_image_names = [image_info.name for image_info in images]
        # image_names = [
        #     get_file_name(image_info.name) + cityscapes_images_suffix + get_file_ext(image_info.name) for
        #     image_info in images
        # ]

        image_names = [
            get_file_name(image_info.name.replace('_leftImg8bit', '')) + \
            cityscapes_images_suffix + get_file_ext(image_info.name) for image_info in images
        ]

        ann_infos = api.annotation.download_batch(dataset.id, image_ids)
        anns = [sly.Annotation.from_json(ann_info.annotation, meta) for ann_info in ann_infos]

        splitter = get_tags_splitter(anns)
        curr_splitter = {'train': 0, 'val': 0, 'test': 0}

        for ann, image_id, image_name, base_image_name in zip(anns, image_ids, image_names, base_image_names):
            train_val_flag = True
            try:
                split_name = ann.img_tags.get('split').value
                if split_name == 'train':
                    image_dir_path = images_dir_path_train
                    ann_dir = anns_dir_path_train
                elif split_name == 'val':
                    image_dir_path = images_dir_path_val
                    ann_dir = anns_dir_path_val
                else:
                    image_dir_path = images_dir_path_test
                    ann_dir = anns_dir_path_test
                    train_val_flag = False
            except:
                ann_tags = [tag.name for tag in ann.img_tags]
                separator_tags = list(set(ann_tags) & set(possible_tags))
                if len(separator_tags) > 1:
                    app_logger.warn('''There are more then one separator tag for {} image. {}
                    tag will be used for split'''.format(image_name, separator_tags[0]))

                if len(separator_tags) >= 1:
                    if separator_tags[0] == 'train':
                        image_dir_path = images_dir_path_train
                        ann_dir = anns_dir_path_train
                    elif separator_tags[0] == 'val':
                        image_dir_path = images_dir_path_val
                        ann_dir = anns_dir_path_val
                    else:
                        image_dir_path = images_dir_path_test
                        ann_dir = anns_dir_path_test
                        train_val_flag = False

                if len(separator_tags) == 0:
                    if curr_splitter['test'] == splitter['test']:
                        curr_splitter = {'train': 0, 'val': 0, 'test': 0}
                    if curr_splitter['train'] < splitter['train']:
                        curr_splitter['train'] += 1
                        image_dir_path = images_dir_path_train
                        ann_dir = anns_dir_path_train
                    elif curr_splitter['val'] < splitter['val']:
                        curr_splitter['val'] += 1
                        image_dir_path = images_dir_path_val
                        ann_dir = anns_dir_path_val
                    elif curr_splitter['test'] < splitter['test']:
                        curr_splitter['test'] += 1
                        image_dir_path = images_dir_path_test
                        ann_dir = anns_dir_path_test
                        train_val_flag = False

            get_image_and_ann()

            progress.iter_done_report()

    sly.fs.archive_directory(RESULT_DIR, RESULT_ARCHIVE)
    app_logger.info("Result directory is archived")

    upload_progress = []
    remote_archive_path = "/cityscapes_format/{}/{}".format(task_id, ARCHIVE_NAME)

    def _print_progress(monitor, upload_progress):
        if len(upload_progress) == 0:
            upload_progress.append(sly.Progress(message="Upload {!r}".format(ARCHIVE_NAME),
                                                total_cnt=monitor.len,
                                                ext_logger=app_logger,
                                                is_size=True))
        upload_progress[0].set_current_value(monitor.bytes_read)

    file_info = api.file.upload(team_id=TEAM_ID,
                                src=RESULT_ARCHIVE,
                                dst=remote_archive_path,
                                progress_cb=lambda m: _print_progress(m, upload_progress))

    app_logger.info("Uploaded to Team-Files: {!r}".format(file_info.full_storage_url))
    api.task.set_output_archive(task_id, file_info.id, ARCHIVE_NAME, file_url=file_info.full_storage_url)

    my_app.stop()


def main():
    sly.logger.info("Script arguments", extra={
        "TEAM_ID": TEAM_ID,
        "WORKSPACE_ID": WORKSPACE_ID,
        "modal.state.slyProjectId": PROJECT_ID
    })

    # Run application service
    my_app.run(initial_events=[{"command": "from_sl_to_cityscapes"}])


if __name__ == '__main__':
    sly.main_wrapper("main", main)
