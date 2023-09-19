"""
works with
!pip install diffusers==0.9.0
!pip install scipy ftfy
!pip install transformers==4.24.0
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from diffusers import (
    AutoencoderKL,
    UNet2DConditionModel
)
from transformers import (
    CLIPTokenizer,
    CLIPTextModel
)
from diffusers import DDPMScheduler
from utils import load_data

device='cuda'
lr=5e-5
batch_size=2
path = '/workspaces/peronal_projects/anime-diffusion/anime-dataset/'
epochs=5

vae = AutoencoderKL.from_pretrained(
    'CompVis/stable-diffusion-v1-4', subfolder='vae').to(device)
tokenizer = CLIPTokenizer.from_pretrained('openai/clip-vit-large-patch14')
text_encoder = CLIPTextModel.from_pretrained('openai/clip-vit-large-patch14').to(device)
unet = UNet2DConditionModel.from_pretrained(
    'CompVis/stable-diffusion-v1-4', subfolder='unet').to(device)

vae.requires_grad_(False)
text_encoder.requires_grad_(False)
optimizer = torch.optim.AdamW(unet.parameters(),lr=lr)

dataset= load_data(path,batch_size)
num_steps_per_epoch = len(dataset)

noise_scheduler = DDPMScheduler.from_pretrained(
    "runwayml/stable-diffusion-v1-5",
    subfolder='scheduler',
)

def get_text_embeds(prompt):
  text_input = tokenizer(
      prompt, padding='max_length', max_length=tokenizer.model_max_length,
      truncation=True, return_tensors='pt')
  with torch.no_grad():
    text_embeddings = text_encoder(text_input.input_ids.to(device))[0]

  uncond_input = tokenizer(
      [''] * len(prompt), padding='max_length',
      max_length=tokenizer.model_max_length, return_tensors='pt')
  with torch.no_grad():
    uncond_embeddings = text_encoder(uncond_input.input_ids.to(device))[0]

  #text_embeddings = torch.cat([uncond_embeddings, text_embeddings])
  return text_embeddings


def train():
    loss = torch.tensor(0.0,device=device)
    for epoch in range(epochs):
        unet.train()
        for _,batch in enumerate(dataset):
            pixel_value = batch[0].to(device)
            caption = batch[1]
            latents = vae.encode(pixel_value).latent_dist.sample()
            latents = latents * 0.18215
            #latents = torch.cat([latents]*2)
            noise = torch.rand_like(latents)
            batch_size = latents.shape[0]
            time_steps = torch.randint(0,noise_scheduler.num_train_timesteps,(batch_size,),device=latents.device)
            time_steps = time_steps.long()
            noisy_latents = noise_scheduler.add_noise(latents,noise,time_steps)
            encoder_hidden_states = get_text_embeds(caption)
            
            noise_pred = unet(noisy_latents,time_steps,encoder_hidden_states,return_dict=False)[0]
            loss = F.mse_loss(noise_pred.float(), noise.float(), reduction="mean")
            optimizer.zero_grad()
            loss.bacward()
            optimizer.step()
            
def test(prompt,init_image=None,num_inference_steps=50,img_per_prompt=5):
    if prompt is not None and isinstance(prompt, str):
        batch_size = 1
    elif prompt is not None and isinstance(prompt, list):
        batch_size = len(prompt)
    height,width = unet.config.sample_size * 0.125,unet.config.sample_size * 0.125
    encoder_hidden_states = get_text_embeds(prompt)
    noise_scheduler.set_timesteps(num_inference_steps, device=device)
    timesteps = noise_scheduler.timesteps
    num_channels_latents = unet.config.in_channels
    if init_image is None:
        init_image = torch.randn((batch_size,num_channels_latents,int(height // 0.125),int(width // 0.125)))
    latents = init_image * 0.18215
    for i,t in enumerate(timesteps):
        latents = noise_scheduler.scale_model_input(latents,t).to(device)
        noise_pred = unet(
            latents,
            t,
            encoder_hidden_states,
            return_dict=False
        )[0]
        latents = noise_scheduler.step(noise_pred,t,latents,return_dict=False)[0]
        break
    image = vae.decode(latents / 0.125,return_dict=False)[0]
test(['testing'])
        
        
    
