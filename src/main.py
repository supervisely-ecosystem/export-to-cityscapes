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
ARCHIVE_NAME = 'Cityscapes.tar.gz'
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
train_to_val_test_coef = 3 / 5
val_test_coef = round((1 - train_to_val_test_coef) / 2, 1)

if train_to_val_test_coef > 1 or train_to_val_test_coef < 0:
    raise ValueError('train_to_val_test_coef should be between 0 and 1, your data is {}'.format(train_to_val_test_coef))


def from_ann_to_cityscapes_mask(ann, name2id, app_logger, test_flag):
    mask_color = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
    mask_label = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
    poly_json = {'imgHeight': ann.img_size[0], 'imgWidth': ann.img_size[1], 'objects': []}
    if test_flag:
        return mask_color, mask_label, poly_json

    for label in ann.labels:
        label.geometry.draw(mask_color, label.obj_class.color)
        label.geometry.draw(mask_label, name2id[label.obj_class.name])
        if type(label.geometry) == Bitmap:
            poly_for_contours = label.geometry.to_contours()[0]
        else:
            poly_for_contours = label.geometry

        if len(poly_for_contours.interior) > 0:
            app_logger.info('Labeled objects must never have holes in cityscapes format, existing holes will be sketched')

        contours = poly_for_contours.exterior_np.tolist()

        if label.obj_class.name == 'out of roi':
            for curr_interior in poly_for_contours.interior_np:
                contours.append(poly_for_contours.exterior_np.tolist()[0])
                contours.extend(curr_interior.tolist())
                contours.append(curr_interior.tolist()[0])

        cityscapes_contours = list(map(lambda cnt: cnt[::-1], contours))
        poly_json['objects'].append({'label': label.obj_class.name, 'polygon': cityscapes_contours})

    return mask_color, mask_label, poly_json



@my_app.callback("from_sl_to_cityscapes")
@sly.timeit
def from_sl_to_cityscapes(api: sly.Api, task_id, context, state, app_logger):

    meta_json = api.project.get_meta(PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)
    for obj_class in meta.obj_classes:
        if obj_class.geometry_type not in possible_geometries:
            raise ValueError('Only converting bitmap and polygon classes is possible, not {}'.format(obj_class.geometry_type))

    RESULT_ARCHIVE = os.path.join(my_app.data_dir, ARCHIVE_NAME)
    RESULT_DIR = os.path.join(my_app.data_dir, RESULT_DIR_NAME)
    result_images_train = os.path.join(RESULT_DIR, images_dir_name, default_dir_train)
    result_images_val = os.path.join(RESULT_DIR, images_dir_name, default_dir_val)
    result_images_test = os.path.join(RESULT_DIR, images_dir_name, default_dir_test)
    result_anns_train = os.path.join(RESULT_DIR, annotations_dir_name, default_dir_train)
    result_anns_val = os.path.join(RESULT_DIR, annotations_dir_name, default_dir_val)
    result_anns_test = os.path.join(RESULT_DIR, annotations_dir_name, default_dir_test)
    sly.fs.mkdir(result_images_train)
    sly.fs.mkdir(result_images_val)
    sly.fs.mkdir(result_images_test)
    sly.fs.mkdir(result_anns_train)
    sly.fs.mkdir(result_anns_val)
    sly.fs.mkdir(result_anns_test)
    app_logger.info("Make Cityscapes format dirs")


    class_to_id = []
    name2id = {}
    for idx, obj_class in enumerate(meta.obj_classes):
        curr_class = {}
        curr_class['label'] = obj_class.name
        curr_class['label_id'] = idx + 1
        curr_class['color'] = obj_class.color
        class_to_id.append(curr_class)
        name2id[obj_class.name] = (idx + 1, idx + 1, idx + 1)

    dump_json_file(class_to_id, os.path.join(RESULT_DIR, 'class_to_id.json'))

    app_logger.info("Create palette, it will be save in class_to_id.json file")

    datasets = api.dataset.get_list(PROJECT_ID)
    for dataset in datasets:
        progress = sly.Progress('Convert images and anns from dataset {}'.format(dataset.name), len(datasets), app_logger)
        images_dir_path_train = os.path.join(result_images_train, dataset.name)
        images_dir_path_val = os.path.join(result_images_val, dataset.name)
        images_dir_path_test = os.path.join(result_images_test, dataset.name)
        anns_dir_path_train = os.path.join(result_anns_train, dataset.name)
        anns_dir_path_val = os.path.join(result_anns_val, dataset.name)
        anns_dir_path_test = os.path.join(result_anns_test, dataset.name)
        mkdir(images_dir_path_train)
        mkdir(images_dir_path_val)
        mkdir(images_dir_path_test)
        mkdir(anns_dir_path_train)
        mkdir(anns_dir_path_val)
        mkdir(anns_dir_path_test)

        images = api.image.get_list(dataset.id)
        if len(images) < 3:
            app_logger.info('Number of images in {} dataset is less then 3, val and train dirs for this dataset may by empty'.format(dataset.name))
        for batch in sly.batched(images):
            image_ids = [image_info.id for image_info in batch]
            base_image_names = [image_info.name for image_info in batch]
            image_names = [get_file_name(image_info.name) + cityscapes_images_suffix + get_file_ext(image_info.name) for image_info in batch]

            train_length = round(len(image_names) * train_to_val_test_coef)
            if len(batch) <= 3:
                train_length = 1
            image_paths_train = [os.path.join(images_dir_path_train, image_name) for image_name in image_names[:train_length]]
            val_length = round(len(image_names) * val_test_coef) + train_length
            image_paths_val = [os.path.join(images_dir_path_val, image_name) for image_name in image_names[train_length:val_length]]
            image_paths_test = [os.path.join(images_dir_path_test, image_name) for image_name in image_names[val_length:]]

            image_paths = image_paths_train + image_paths_val + image_paths_test
            api.image.download_paths(dataset.id, image_ids, image_paths)


            for im_path in image_paths:
                if get_file_ext(im_path) != '.png':
                    im = Image.open(im_path).convert('RGB')
                    im.save(im_path[:-1 * len(get_file_ext(im_path))] + '.png')
                    silent_remove(im_path)

            ann_infos = api.annotation.download_batch(dataset.id, image_ids)
            anns = [sly.Annotation.from_json(ann_info.annotation, meta) for ann_info in ann_infos]

            test_flag = False
            for idx, (ann, image_name) in enumerate(zip(anns, base_image_names)):

                if idx < train_length:
                    ann_dir = anns_dir_path_train
                elif idx >= train_length and idx < val_length:
                    ann_dir = anns_dir_path_val
                else:
                    ann_dir = anns_dir_path_test
                    test_flag = True

                mask_color, mask_label, poly_json = from_ann_to_cityscapes_mask(ann, name2id, app_logger, test_flag)
                dump_json_file(poly_json, os.path.join(ann_dir, get_file_name(image_name) + cityscapes_polygons_suffix))
                write(os.path.join(ann_dir, get_file_name(image_name) + cityscapes_color_suffix), mask_color)
                write(os.path.join(ann_dir, get_file_name(image_name) + cityscapes_labels_suffix), mask_label)

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

    file_info = api.file.upload(TEAM_ID, RESULT_ARCHIVE, remote_archive_path, lambda m: _print_progress(m, upload_progress))
    app_logger.info("Uploaded to Team-Files: {!r}".format(file_info.full_storage_url))
    api.task.set_output_archive(task_id, file_info.id, ARCHIVE_NAME, file_url=file_info.full_storage_url)


    my_app.stop()



def main():
    sly.logger.info("Script arguments", extra={
        "TEAM_ID": TEAM_ID,
        "WORKSPACE_ID": WORKSPACE_ID,
        "PROJECT_ID": PROJECT_ID
    })

    # Run application service
    my_app.run(initial_events=[{"command": "from_sl_to_cityscapes"}])



if __name__ == '__main__':
        sly.main_wrapper("main", main)

