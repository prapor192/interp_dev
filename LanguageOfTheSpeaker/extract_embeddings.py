import argparse
import os
from pathlib import Path

import chromadb
import numpy as np
import torch
import wespeaker
import json

def get_audio_path(json_file, dataset_dir):
    """
    Recursively finds all audio files in the specified directory.
    """
    dataset_dir = Path(dataset_dir)
    
    with open(json_file, "r") as f:
        data = json.load(f)
    
    audio_files = []
    for item in data:
        filename = item["filename"]
        
        for lang_dir in dataset_dir.iterdir():
            potential_path = lang_dir / filename
            if potential_path.exists():
                audio_files.append(potential_path)
                break
        
    return audio_files



def extract_embeddings(audio_files, device, pretrain_dir):
    """
    Extracts embeddings from audio files using the WeSpeaker model
    """
    model = wespeaker.load_model_local(pretrain_dir)
    model.set_device(device)

    embeddings = []

    for file_path in audio_files:
        embedding = model.extract_embedding(file_path)

        embedding = embedding.cpu().numpy()
        embeddings.append({
            'file_path': str(file_path),
            'embedding': embedding
        })

    return embeddings


def assign_labels(embeddings):
    """
    Assigns labels to classes. In this case, by the name of the parent folder.
    """
    for emb in embeddings:
        parent_folder = Path(emb['file_path']).parent.name
        emb['label'] = parent_folder


def save_to_npy(embeddings, save_dir):
    """
    Saves embeddings in .npy format.
    """
    numpy_embs = np.array(embeddings)
    np.save(os.path.join(save_dir, "numpy_embs.npy"), numpy_embs)


def save_to_chromadb(embeddings, db_path, split):
    """
    Stores embeddings in ChromaDB
    """
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(name="gender_embeddings")

    collection.add(
        ids=[f"{split}_{i}" for i in range(len(embeddings))],
        embeddings=[item['embedding'] for item in embeddings],
        metadatas=[{
            "file_path": item['file_path'], "label": item['label'],
            "split": split
        }
            for item in embeddings]
    )

def load_label_map(json_file):
    """
    Loads the label map from a JSON file.
    """
    with open(json_file, 'r') as f:
        return json.load(f)
    
def main():
    """
    Main function
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset_dir", type=str, default="./dataset",
                        help="Path to dataset")
    parser.add_argument("--train_dir", type=str, default="./train_audio",
                        help="Path to train.json")
    parser.add_argument("--test_dir", type=str, default="./test_audio",
                        help="Path to test.json")
    parser.add_argument("--pretrain_dir", type=str, default="./pretrain_dir",
                        help="Path to wespeaker model pretrain_dir.")
    parser.add_argument("--output", type=str, required=True,
                        choices=["npy", "chromadb"],
                        help="Embeddings saving format: npy or chromadb.")
    parser.add_argument("--save_path", type=str, default="./embeddings",
                        help="Save path for calculated embeddings")
    args = parser.parse_args()

    if not os.path.exists(args.train_dir):
        raise FileNotFoundError(f"Folder {args.train_dir} does not exists.")
    if not os.path.exists(args.test_dir):
        raise FileNotFoundError(f"Folder {args.test_dir} does not exists.")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_audio_files = get_audio_path(args.train_dir, args.dataset_dir)
    test_audio_files = get_audio_path(args.test_dir, args.dataset_dir)

    train_embeddings = extract_embeddings(train_audio_files, device,
                                          args.pretrain_dir)
    test_embeddings = extract_embeddings(test_audio_files, device,
                                         args.pretrain_dir)

    assign_labels(train_embeddings)
    assign_labels(test_embeddings)

    if args.output == "npy":
        os.makedirs(args.save_path, exist_ok=True)
        embeddings = [{"train": train_embeddings, "test": test_embeddings}]
        save_to_npy(embeddings, args.save_path)
    elif args.output == "chromadb":
        save_to_chromadb(train_embeddings, args.save_path, split="train")
        save_to_chromadb(test_embeddings, args.save_path, split="test")


if __name__ == '__main__':
    main()
