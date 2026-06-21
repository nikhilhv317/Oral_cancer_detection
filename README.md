# End-to-End Oral Lesion Detection Pipeline

**Advanced AI System for Oral Lesion Detection with Attention Mechanisms** — Optimized for **Edge Devices** and **Clinical Desktop Deployment**.

## Project Overview

A complete **end-to-end deep learning pipeline** for detecting oral lesions in clinical images. The system evolved through multiple architectures and culminated in a highly efficient cascaded hybrid model designed for real-world clinical use.

## Key Features & Achievements

- **Model Evolution**:
  - Initial implementation using **Faster R-CNN (ResNet50-FPN)**
  - Evaluated **YOLOv5** (classification) and **YOLOv8** (detection)
  - Final model showed superior accuracy and significantly faster inference speed

- **Hybrid Cascaded Architecture**:
  - Lightweight **GhostNet** backbone enhanced with **CBAM (Convolutional Block Attention Module)**
  - Multi-class classification followed by conditional **YOLOv8** lesion detection
  - Reduces unnecessary computation by running detection only on positive cases

- **Performance**:
  - Achieved **98.9% Precision**, **98.89% Recall**, and **98.88% F1-Score**
  - **~14% overall performance improvement** over baseline models

- **Desktop Application**:
  - Custom **PyQt6** cross-platform GUI tailored for clinical workflows
  - Features: Image upload, real-time bounding box visualization, confidence scoring, and automated diagnostic report generation

- **Deployment**:
  - **Windows**: Packaged as standalone `.exe` installer using **PyInstaller + Inno Setup**
  - **Linux ARM64**: Built as `.deb` package for edge devices (Rockchip, Orange Pi, etc.)

## Tech Stack

- **Deep Learning**: PyTorch, YOLOv8, GhostNet, CBAM, Faster R-CNN
- **Computer Vision**: OpenCV
- **GUI**: PyQt6
- **Deployment**: PyInstaller, Inno Setup, Linux packaging tools

## Project Structure
