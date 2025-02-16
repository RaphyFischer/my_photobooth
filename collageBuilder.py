import os
import numpy as np
import globals
from PIL import Image, ImageChops, ImageOps


class CollageRenderer:

    def fit_image_to_placeholder(self,image, placeholder_size):
        return ImageOps.fit(image, placeholder_size, Image.LANCZOS)

    def renderImagesToCollage(self, collage: globals.Collage, targetFile: str):
        # Load the collage template
        collage_template_path = os.path.join(os.path.dirname(__file__), "ui", "collages", collage.name)
        collage_template = Image.open(collage_template_path).convert("RGBA")
        if collage_template is None:
            print(f"Failed to read collage template: {collage_template_path}")
            return
        
        # Render the images to the collage
        for imagePosition in collage.images:
            fullPath = os.path.join(os.path.dirname(__file__), imagePosition.imagePath)
            print(fullPath)
            image = Image.open(fullPath).convert("RGBA")
            rotated_image = image.rotate(imagePosition.angle, expand=True, resample=Image.BICUBIC)
            placeholder_size = (imagePosition.size.width, imagePosition.size.height)
            fitted_image = self.fit_image_to_placeholder(rotated_image, placeholder_size)
            
        # Create a new image with the same size as the template
            result = Image.new("RGBA", collage_template.size)

            # Paste the template onto the result image
            result.paste(collage_template, (0, 0), collage_template)

            # Paste the rotated and trimmed image onto the result
            result.paste(fitted_image, (imagePosition.position.x, imagePosition.position.y), fitted_image)

            result.paste(fitted_image, (imagePosition.position.x + imagePosition.offset, imagePosition.position.y), fitted_image)

            collage_template = result

        
        # Save the final collage
        # Convert the result to RGB mode
        result_rgb = collage_template.convert('RGB')

        # Save the result as JPG
        result_rgb.save(targetFile, "JPEG")
