import json
import os
import sys

from . import ipc
from . import uploader
from .exif_aux import verify_mapillary_tag


def upload(
    import_path,
    skip_subfolders=False,
    number_threads=None,
    max_attempts=None,
    video_import_path=None,
):
    """
    Upload local images to Mapillary
    Args:
        import_path: Directory path to where the images are stored.
        verbose: Print extra warnings and errors.
        skip_subfolders: Skip images stored in subdirectories.

    Returns:
        Images are uploaded to Mapillary and flagged locally as uploaded.
    """

    # in case of video processing, adjust the import path
    if video_import_path:
        # sanity check if video file is passed
        if not os.path.isdir(video_import_path) and not os.path.isfile(
            video_import_path
        ):
            print(
                "Error, video path " + video_import_path + " does not exist, exiting..."
            )
            sys.exit(1)

        # set sampling path
        video_sampling_path = "mapillary_sampled_video_frames"
        video_dirname = (
            video_import_path
            if os.path.isdir(video_import_path)
            else os.path.dirname(video_import_path)
        )
        import_path = (
            os.path.join(os.path.abspath(import_path), video_sampling_path)
            if import_path
            else os.path.join(os.path.abspath(video_dirname), video_sampling_path)
        )

    # basic check for all
    if not import_path or not os.path.isdir(import_path):
        print(f"Error, import directory {import_path} does not exist, exiting...")
        sys.exit(1)

    # get list of file to process
    total_file_list = uploader.get_total_file_list(import_path, skip_subfolders)
    upload_file_list = uploader.get_upload_file_list(import_path, skip_subfolders)
    failed_file_list = uploader.get_failed_upload_file_list(
        import_path, skip_subfolders
    )
    success_file_list = uploader.get_success_upload_file_list(
        import_path, skip_subfolders
    )
    to_finalize_file_list = uploader.get_finalize_file_list(
        import_path, skip_subfolders
    )

    if len(success_file_list) == len(total_file_list):
        print("All images have already been uploaded")
    else:
        if len(failed_file_list):
            upload_failed = (
                input("Retry uploading previously failed image uploads? [y/n]: ")
                if not ipc.is_enabled()
                else "y"
            )
            # if yes, add images to the upload list
            if upload_failed in ["y", "Y", "yes", "Yes"]:
                upload_file_list.extend(failed_file_list)

        # verify the images in the upload list, they need to have the image
        # description and certain MAP properties
        upload_file_list = [f for f in upload_file_list if verify_mapillary_tag(f)]

        if not len(upload_file_list) and not len(to_finalize_file_list):
            print("No images to upload.")
            print(
                'Please check if all images contain the required Mapillary metadata. If not, you can use "mapillary_tools process" to add them'
            )
            sys.exit(1)

        if upload_file_list:
            # get upload params for the manual upload images, group them per sequence
            # and separate direct upload images
            params = {}
            list_per_sequence_mapping = {}
            direct_upload_file_list = []
            for image in upload_file_list:
                log_root = uploader.log_rootpath(image)
                upload_params_path = os.path.join(
                    log_root, "upload_params_process.json"
                )
                if os.path.isfile(upload_params_path):
                    with open(upload_params_path, "rb") as jf:
                        params[image] = json.load(jf)
                        sequence = params[image]["key"]
                        list_per_sequence_mapping.setdefault(sequence, []).append(image)
                else:
                    direct_upload_file_list.append(image)

            # inform how many images are to be uploaded and how many are being skipped
            # from upload

            print(
                f"Uploading {len(upload_file_list)} images with valid mapillary tags (Skipping {len(total_file_list) - len(upload_file_list)})"
            )

            if direct_upload_file_list:
                uploader.upload_file_list_direct(
                    direct_upload_file_list, number_threads, max_attempts
                )

            for idx, sequence_uuid in enumerate(list_per_sequence_mapping):
                uploader.upload_file_list_manual(
                    list_per_sequence_mapping[sequence_uuid],
                    sequence_uuid,
                    params,
                    idx,
                    number_threads,
                    max_attempts,
                )

        if to_finalize_file_list:
            params = {}
            sequences = []
            for image in to_finalize_file_list:
                log_root = uploader.log_rootpath(image)
                upload_params_path = os.path.join(
                    log_root, "upload_params_process.json"
                )
                if os.path.isfile(upload_params_path):
                    with open(upload_params_path, "rb") as jf:
                        image_params = json.load(jf)
                        sequence = image_params["key"]
                        if sequence not in sequences:
                            params[image] = image_params
                            sequences.append(sequence)

            uploader.flag_finalization(to_finalize_file_list)

    uploader.print_summary(upload_file_list)
