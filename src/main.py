import os
import numpy as np
import supervisely_lib as sly
from supervisely_lib.imaging.image import write
from supervisely_lib.io.fs import mkdir, get_file_name
from supervisely_lib.io.json import dump_json_file


my_app = sly.AppService()

TEAM_ID = int(os.environ['context.teamId'])
WORKSPACE_ID = int(os.environ['context.workspaceId'])
PROJECT_ID = int(os.environ['modal.state.slyProjectId'])
ARCHIVE_NAME = 'Cityscapes.tar.gz'
RESULT_DIR_NAME = 'cityscapes_format'
images_dir_name = 'leftImg8bit'
annotations_dir_name = 'gtFine'



def from_ann_to_cityscapes_mask(ann, name2id):
    mask_color = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
    mask_label = np.zeros((ann.img_size[0], ann.img_size[1], 3), dtype=np.uint8)
    poly_json = {'imgHeight': ann.img_size[0], 'imgWidth': ann.img_size[1], 'objects': []}
    for label in ann.labels:
        label.geometry.draw(mask_color, label.obj_class.color)
        label.geometry.draw(mask_label, name2id[label.obj_class.name])
        contours = label.geometry.to_contours()[0]
        poly_json['objects'].append({'label': label.obj_class.name, 'polygon': contours.exterior_np.tolist()})

    return mask_color, mask_label, poly_json


@my_app.callback("from_sl_to_cityscapes")
@sly.timeit
def from_sl_to_cityscapes(api: sly.Api, task_id, context, state, app_logger):

    meta_json = api.project.get_meta(PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)


    RESULT_ARCHIVE = os.path.join(my_app.data_dir, ARCHIVE_NAME)
    RESULT_DIR = os.path.join(my_app.data_dir, RESULT_DIR_NAME)
    result_images_dir = os.path.join(RESULT_DIR, images_dir_name)
    result_annotations_dir = os.path.join(RESULT_DIR, annotations_dir_name)
    sly.fs.mkdir(result_images_dir)
    sly.fs.mkdir(result_annotations_dir)
    app_logger.info("Make Cityscapes format dirs")

    name2id = {}
    for idx, obj_class in enumerate(meta.obj_classes):
        name2id[obj_class.name] = (idx + 1, idx + 1, idx + 1)

    app_logger.info("Create palette") #TODO Is need to print palette?


    datasets = api.dataset.get_list(PROJECT_ID)
    for dataset in datasets:
        progress = sly.Progress('Convert images and anns from dataset {}'.format(dataset.name), len(datasets), app_logger)
        images_dir_path = os.path.join(result_images_dir, dataset.name)
        annotations_dir_path = os.path.join(result_annotations_dir, dataset.name)
        mkdir(images_dir_path)
        mkdir(annotations_dir_path)

        images = api.image.get_list(dataset.id)
        for batch in sly.batched(images):
            image_ids = [image_info.id for image_info in batch]
            image_names = [image_info.name for image_info in batch]
            image_paths = [os.path.join(images_dir_path, image_name) for image_name in image_names]
            api.image.download_paths(dataset.id, image_ids, image_paths)

            ann_infos = api.annotation.download_batch(dataset.id, image_ids)
            anns = [sly.Annotation.from_json(ann_info.annotation, meta) for ann_info in ann_infos]

            for ann, image_name in zip(anns, image_names):
                mask_color, mask_label, poly_json = from_ann_to_cityscapes_mask(ann, name2id)

                dump_json_file(poly_json, os.path.join(annotations_dir_path, get_file_name(image_name) + '_polygons.json'))
                write(os.path.join(annotations_dir_path, get_file_name(image_name) + '_color.png'), mask_color)
                write(os.path.join(annotations_dir_path, get_file_name(image_name) + '_labelIds.png'), mask_label)

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
