import gphoto2 as gp
error, camera = gp.gp_camera_new()
error = gp.gp_camera_init(camera)
error, text = gp.gp_camera_get_summary(camera)
print('Summary')
print('=======')
print(text.text)
error = gp.gp_camera_exit(camera)
